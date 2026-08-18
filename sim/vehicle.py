"""The simulated vehicle.

A permanent test fixture, not a throwaway. It implements the same LINK
client and the same task state machine a real machine runs, with fake
movement and scripted observations in place of motors and a camera. The
world model must not be able to tell it apart from a real vehicle by
inspecting messages, so everything it sends is a fully formed contract
message and nothing marks it as simulated.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from link.v1.messages_pb2 import TaskAssignment
from link.v1.ontology_pb2 import AssetStatus, Observation, Position, Task, TaskState
from ulid import ULID

from sim import geo
from sim.link_client import LinkClient, timestamp_now

log = logging.getLogger(__name__)

# How close counts as arrived, in meters.
ARRIVAL_TOLERANCE_M = 2.0

# What a vehicle can do when its scenario does not say. The value a real
# machine's reference manifest carries, so the default sim behaves like
# the default machine.
DEFAULT_TASK_TYPES = ("navigate", "patrol", "hold", "return_home")


@dataclass
class ScriptedObservation:
    """Something the simulated sensor will report."""

    after_seconds: float
    entity_class: str
    confidence: float
    offset_north_m: float = 0.0
    offset_east_m: float = 0.0
    narration: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    repeat_every_seconds: float = 0.0
    count: int = 1

    # Assigned at load time so every report of the same scripted thing
    # carries one identity, exactly as a real machine's local tracker would.
    entity_id: str = ""
    sent: int = 0
    next_at: float = 0.0


@dataclass
class VehicleConfig:
    asset_id: str
    asset_class: str
    name: str
    start_latitude_deg: float
    start_longitude_deg: float
    speed_mps: float = 2.5
    heartbeat_hz: float = 1.0
    telemetry_hz: float = 5.0
    battery_start: float = 0.92
    battery_drain_per_minute: float = 0.004
    capabilities: dict[str, Any] = field(default_factory=dict)
    # What this vehicle can be ordered to do. Scenario data, not code: the
    # same value drives the accept/refuse behavior and the declaration the
    # world model sees, so the two cannot drift apart (the reverse-modeling
    # fix). A task type outside this tuple is refused in words.
    supported_task_types: tuple[str, ...] = DEFAULT_TASK_TYPES
    observations: list[ScriptedObservation] = field(default_factory=list)
    patrol_laps: int = 1
    # What this machine says about its own orders. Loaded from the machine's
    # language file so a deployment can change the words without reflashing.
    messages: dict[str, str] = field(default_factory=dict)

    def say(self, key: str) -> str:
        return self.messages.get(key, "")

    def declared_capabilities(self) -> dict[str, Any]:
        """What this vehicle tells the world model it is and can do.

        The same shape a real machine's manifest declares (comma-joined
        task types, name as data), built from the same fields that drive
        behavior. Anything else the scenario declared passes through.
        """
        declared = dict(self.capabilities)
        declared.setdefault("name", self.name)
        declared["supported_task_types"] = ", ".join(self.supported_task_types)
        return declared


class SimulatedVehicle:
    """Movement, task execution, and reporting for one simulated machine."""

    def __init__(self, config: VehicleConfig, client: LinkClient):
        self.cfg = config
        self.client = client

        self.latitude = config.start_latitude_deg
        self.longitude = config.start_longitude_deg
        self.home = (config.start_latitude_deg, config.start_longitude_deg)
        self.heading_deg = 0.0
        self.speed_mps = 0.0
        self.battery = config.battery_start
        self.status = AssetStatus.ASSET_STATUS_STANDBY

        self.task: Task | None = None
        self.route: list[tuple[float, float]] = []
        self.route_index = 0
        self.route_total_m = 0.0
        self.route_done_m = 0.0
        self.laps_remaining = 0

        self._orders: queue.Queue[TaskAssignment] = queue.Queue()
        self._stop = threading.Event()
        self._started_at = 0.0

    # -- lifecycle ---------------------------------------------------------

    def on_task(self, assignment: TaskAssignment) -> None:
        """Called from the link client's thread. Hands off and returns."""
        self._orders.put(assignment)

    def stop(self) -> None:
        self._stop.set()

    def run(self, duration_s: float | None = None) -> None:
        """Run the vehicle until stopped."""
        self._started_at = time.monotonic()
        for scripted in self.cfg.observations:
            scripted.entity_id = str(ULID())
            scripted.next_at = scripted.after_seconds

        tick = 0.05
        last_heartbeat = 0.0
        last_telemetry = 0.0
        last_move = time.monotonic()

        # Declare what this machine is and can do, the way a real
        # machine's registry rides up: in a telemetry payload (D-8). The
        # client remembers the declaration and repeats it on every
        # connect, so a link that is down at boot, or drops later, never
        # leaves the platform without it.
        self._send_telemetry(declare=True)

        while not self._stop.is_set():
            now = time.monotonic()
            elapsed = now - self._started_at

            self._drain_orders()

            dt = now - last_move
            last_move = now
            self._move(dt)
            self._drain_battery(dt)
            self._fire_observations(elapsed)

            if now - last_heartbeat >= 1.0 / self.cfg.heartbeat_hz:
                last_heartbeat = now
                self._send_heartbeat()

            moving = self.speed_mps > 0.0
            telemetry_period = 1.0 / self.cfg.telemetry_hz if moving else 1.0
            if now - last_telemetry >= telemetry_period:
                last_telemetry = now
                self._send_telemetry()

            if duration_s is not None and elapsed >= duration_s:
                break
            time.sleep(tick)

    # -- orders ------------------------------------------------------------

    def _drain_orders(self) -> None:
        while True:
            try:
                assignment = self._orders.get_nowait()
            except queue.Empty:
                return
            self._accept_or_refuse(assignment.task)

    def _accept_or_refuse(self, task: Task) -> None:
        if task.status == TaskState.TASK_STATE_CANCELLED:
            if self.task is not None and task.task_id == self.task.task_id:
                self._finish(TaskState.TASK_STATE_CANCELLED, self.cfg.say("cancelled"))
            return

        if task.task_type not in self.cfg.supported_task_types:
            self.client.task_status(
                task_id=task.task_id,
                status=TaskState.TASK_STATE_FAILED,
                progress=0.0,
                message=self.cfg.say("cannot_do_that"),
            )
            return

        route = self._route_for(task)
        if route is None:
            self.client.task_status(
                task_id=task.task_id,
                status=TaskState.TASK_STATE_FAILED,
                progress=0.0,
                message=self.cfg.say("no_destination"),
            )
            return

        self.task = task
        self.route = route
        self.route_index = 0
        self.route_done_m = 0.0
        self.route_total_m = self._route_length(route)
        self.laps_remaining = self._laps_for(task)
        self.status = AssetStatus.ASSET_STATUS_ACTIVE

        self.client.task_status(
            task_id=task.task_id,
            status=TaskState.TASK_STATE_ACCEPTED,
            progress=0.0,
            message=self.cfg.say("accepted"),
        )
        self.client.task_status(
            task_id=task.task_id,
            status=TaskState.TASK_STATE_RUNNING,
            progress=0.0,
            message=self.cfg.say("running"),
            eta_sec=self._eta_sec(),
        )

    def _route_for(self, task: Task) -> list[tuple[float, float]] | None:
        if task.task_type == "hold":
            return []
        if task.task_type == "return_home":
            return [self.home]

        waypoints = [(w.latitude_deg, w.longitude_deg) for w in task.parameters.waypoints]
        if not waypoints:
            return None
        if task.task_type == "patrol":
            # A patrol ends where it began, so the loop closes.
            waypoints = waypoints + [waypoints[0]]
        return waypoints

    def _laps_for(self, task: Task) -> int:
        if task.task_type != "patrol":
            return 1
        extras = task.parameters.extras
        if "laps" in extras.fields:
            value = extras.fields["laps"]
            if value.HasField("number_value"):
                return max(1, int(value.number_value))
        return self.cfg.patrol_laps

    def _route_length(self, route: list[tuple[float, float]]) -> float:
        if not route:
            return 0.0
        total = 0.0
        point = (self.latitude, self.longitude)
        for waypoint in route:
            total += geo.distance_m(point[0], point[1], waypoint[0], waypoint[1])
            point = waypoint
        return total

    # -- movement ----------------------------------------------------------

    def _move(self, dt: float) -> None:
        if self.task is None or not self.route or self.route_index >= len(self.route):
            self.speed_mps = 0.0
            if self.task is not None and self.task.task_type == "hold":
                self.status = AssetStatus.ASSET_STATUS_ACTIVE
            return

        target_lat, target_lon = self.route[self.route_index]
        remaining = geo.distance_m(self.latitude, self.longitude, target_lat, target_lon)

        if remaining <= ARRIVAL_TOLERANCE_M:
            self.route_index += 1
            if self.route_index >= len(self.route):
                self.laps_remaining -= 1
                if self.laps_remaining > 0:
                    self.route_index = 0
                    self.route_done_m = 0.0
                else:
                    self._finish(TaskState.TASK_STATE_DONE, self.cfg.say("finished"))
            return

        step = min(self.cfg.speed_mps * dt, remaining)
        self.heading_deg = geo.bearing_deg(self.latitude, self.longitude, target_lat, target_lon)
        self.latitude, self.longitude = geo.step_toward(
            self.latitude, self.longitude, target_lat, target_lon, step
        )
        self.speed_mps = self.cfg.speed_mps
        self.route_done_m += step

        self._report_progress()

    def _report_progress(self) -> None:
        if self.task is None:
            return
        # Progress is only reported on meaningful change, so the feed and
        # the wire stay quiet while nothing is happening.
        progress = self._progress()
        if progress - getattr(self, "_last_progress", -1.0) < 0.05:
            return
        self._last_progress = progress
        self.client.task_status(
            task_id=self.task.task_id,
            status=TaskState.TASK_STATE_RUNNING,
            progress=progress,
            message=self.cfg.say("running"),
            eta_sec=self._eta_sec(),
        )

    def _progress(self) -> float:
        if self.route_total_m <= 0:
            return 1.0
        return max(0.0, min(1.0, self.route_done_m / self.route_total_m))

    def _eta_sec(self) -> int:
        if self.cfg.speed_mps <= 0:
            return 0
        remaining = max(0.0, self.route_total_m - self.route_done_m)
        return int(remaining / self.cfg.speed_mps)

    def _finish(self, state: int, message: str) -> None:
        if self.task is None:
            return
        self.client.task_status(
            task_id=self.task.task_id,
            status=state,
            progress=1.0 if state == TaskState.TASK_STATE_DONE else self._progress(),
            message=message,
        )
        self.task = None
        self.route = []
        self.route_index = 0
        self.speed_mps = 0.0
        self._last_progress = -1.0
        self.status = AssetStatus.ASSET_STATUS_STANDBY

    def _drain_battery(self, dt: float) -> None:
        self.battery = max(0.0, self.battery - self.cfg.battery_drain_per_minute * (dt / 60.0))

    # -- sensing -----------------------------------------------------------

    def _fire_observations(self, elapsed: float) -> None:
        for scripted in self.cfg.observations:
            if scripted.sent >= scripted.count or elapsed < scripted.next_at:
                continue

            lat, lon = geo.offset(
                self.latitude, self.longitude, scripted.offset_north_m, scripted.offset_east_m
            )
            observation = Observation(
                observation_id=str(ULID()),
                entity_id=scripted.entity_id,
                asset_id=self.cfg.asset_id,
                position=Position(latitude_deg=lat, longitude_deg=lon),
                confidence=scripted.confidence,
                entity_class=scripted.entity_class,
                narration=scripted.narration,
                timestamp=timestamp_now(),
            )
            for key, value in scripted.attributes.items():
                observation.attributes[key] = value

            self.client.observation(observation)
            scripted.sent += 1
            scripted.next_at = elapsed + (scripted.repeat_every_seconds or 1e9)

    # -- reporting ---------------------------------------------------------

    def _position(self) -> Position:
        return Position(latitude_deg=self.latitude, longitude_deg=self.longitude)

    def _send_heartbeat(self) -> None:
        self.client.heartbeat(
            asset_class=self.cfg.asset_class,
            status=self.status,
            battery_fraction=self.battery,
            position=self._position(),
            current_task_id=self.task.task_id if self.task else "",
        )

    def _send_telemetry(self, declare: bool = False) -> None:
        payload = None
        if declare:
            payload = {"registry": {"manifest": self.cfg.declared_capabilities()}}
        self.client.telemetry(
            position=self._position(),
            heading_deg=self.heading_deg,
            speed_mps=self.speed_mps,
            payload=payload,
        )
