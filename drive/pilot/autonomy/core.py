"""The autonomy core.

One loop. It takes orders, plans them, drives the navigator, watches the
sensors, and reports what is happening. It is the same program on every
machine, which is the whole claim the HAL makes.

Three things it deliberately does not do:

* It does not know what kind of machine it is on. Everything that would
  differ lives in the manifest or behind a driver.
* It does not check whether the link is up before deciding what to do. The
  disconnection law means the answer would not change its behaviour, so
  asking would only invite code that behaves differently when watched.
* It does not put words in Python. Every sentence an operator can read
  comes from the language file, so a deployment can change how its machines
  speak without reflashing them.
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

from pilot import geo
from pilot.autonomy.navigator import Navigator
from pilot.autonomy.worldslice import WorldSlice
from pilot.hal.interfaces import Waypoint
from pilot.hal.loader import DriverSet
from pilot.hal.manifest import Manifest
from pilot.link_client import LinkClient, timestamp_now

log = logging.getLogger(__name__)

# How often the machine recomposes what its hardware layer knows. Driver
# health checks and bus scans are cheap but not free, and a machine's
# insides do not change at loop rate.
REGISTRY_INTERVAL_S = 1.0


@dataclass
class RuntimeConfig:
    """Timings and words. Everything else comes from the manifest."""

    heartbeat_hz: float = 1.0
    telemetry_hz: float = 5.0
    tick_s: float = 0.05
    patrol_laps: int = 1
    messages: dict[str, str] = field(default_factory=dict)

    def say(self, key: str) -> str:
        return self.messages.get(key, "")


class AutonomyCore:
    """Task execution, sensing, and reporting for one machine."""

    def __init__(
        self,
        manifest: Manifest,
        drivers: DriverSet,
        navigator: Navigator,
        link: LinkClient,
        config: RuntimeConfig,
    ):
        self.manifest = manifest
        self.drivers = drivers
        self.navigator = navigator
        self.link = link
        self.cfg = config

        self.world = WorldSlice()
        self.status = AssetStatus.ASSET_STATUS_STANDBY
        self.battery = manifest.battery_start_fraction

        self._orders: queue.Queue[TaskAssignment] = queue.Queue()
        self._stop = threading.Event()
        self._last_progress = -1.0
        self._laps_remaining = 0

    # -- lifecycle ---------------------------------------------------------

    def on_task(self, assignment: TaskAssignment) -> None:
        """Called from the comms driver's thread. Hands off and returns."""
        self._orders.put(assignment)

    def stop(self) -> None:
        self._stop.set()

    def run(self, duration_s: float | None = None) -> None:
        started = time.monotonic()
        pose = self.drivers.locomotion.pose()
        self.world.home = (pose.latitude_deg, pose.longitude_deg)

        last_heartbeat = 0.0
        last_telemetry = 0.0
        last_registry = 0.0
        last_tick = time.monotonic()

        while not self._stop.is_set():
            now = time.monotonic()
            dt = now - last_tick
            last_tick = now

            self._drain_orders()
            self.navigator.step(dt)
            self._advance_task()
            self._drain_battery(dt)
            self._sense()

            # Composing a registry snapshot polls every driver's health and
            # rescans its buses, which is not something to do at loop rate.
            # Once a second is far more often than a machine's insides
            # change, and the client still only puts it on the wire when
            # something actually did.
            if now - last_registry >= REGISTRY_INTERVAL_S:
                last_registry = now
                self.link.offer_registry(self.drivers.registry.snapshot())

            if now - last_heartbeat >= 1.0 / self.cfg.heartbeat_hz:
                last_heartbeat = now
                self._send_heartbeat()

            moving = self.drivers.locomotion.pose().speed_mps > 0.0
            period = 1.0 / self.cfg.telemetry_hz if moving else 1.0
            if now - last_telemetry >= period:
                last_telemetry = now
                self._send_telemetry()

            if duration_s is not None and now - started >= duration_s:
                break
            time.sleep(self.cfg.tick_s)

    # -- orders ------------------------------------------------------------

    def _drain_orders(self) -> None:
        while True:
            try:
                assignment = self._orders.get_nowait()
            except queue.Empty:
                return
            self._accept_or_refuse(assignment.task)

    def _accept_or_refuse(self, task: Task) -> None:
        current = self.world.current_task

        if task.status == TaskState.TASK_STATE_CANCELLED:
            if current is not None and task.task_id == current.task_id:
                self.navigator.cancel()
                self._finish(TaskState.TASK_STATE_CANCELLED, self.cfg.say("cancelled"))
            return

        if task.task_type not in self.manifest.supported_task_types:
            # Refused in words, never dropped. The contract requires it and
            # an operator left wondering is worse than one told no.
            self.link.task_status(
                task_id=task.task_id,
                status=TaskState.TASK_STATE_FAILED,
                progress=0.0,
                message=self.cfg.say("cannot_do_that"),
            )
            return

        route = self._route_for(task)
        if route is None:
            self.link.task_status(
                task_id=task.task_id,
                status=TaskState.TASK_STATE_FAILED,
                progress=0.0,
                message=self.cfg.say("no_destination"),
            )
            return

        self.world.current_task = task
        self._laps_remaining = self._laps_for(task)
        self._last_progress = -1.0
        self.status = AssetStatus.ASSET_STATUS_ACTIVE
        self.navigator.follow(route)

        self.link.task_status(
            task_id=task.task_id,
            status=TaskState.TASK_STATE_ACCEPTED,
            progress=0.0,
            message=self.cfg.say("accepted"),
        )
        self.link.task_status(
            task_id=task.task_id,
            status=TaskState.TASK_STATE_RUNNING,
            progress=0.0,
            message=self.cfg.say("running"),
            eta_sec=self._eta_sec(),
        )

    def _route_for(self, task: Task) -> list[Waypoint] | None:
        if task.task_type == "hold":
            return []
        if task.task_type == "return_home":
            if self.world.home is None:
                return None
            return [Waypoint(self.world.home[0], self.world.home[1])]

        waypoints = [
            Waypoint(
                latitude_deg=w.latitude_deg,
                longitude_deg=w.longitude_deg,
                altitude_m=w.altitude_m if w.HasField("altitude_m") else None,
            )
            for w in task.parameters.waypoints
        ]
        # No navigator in this build acts on altitude. Saying so is better
        # than appearing to have obeyed: silently ignoring part of an order
        # is how a machine ends up trusted for something it never did.
        #
        # The wording is about this navigator, not about the machine. What
        # kind of body this is remains something the core does not know and
        # must not guess at.
        if any(w.altitude_m is not None for w in waypoints):
            log.warning(
                "%s was given a waypoint with an altitude, and this build's navigator "
                "does not act on altitude, so it will move to the position and ignore "
                "the height",
                self.manifest.name,
            )
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

    def _advance_task(self) -> None:
        task = self.world.current_task
        if task is None:
            return

        if task.task_type == "hold":
            self.status = AssetStatus.ASSET_STATUS_ACTIVE
            return

        # A navigator that has given up is reported at once. The alternative
        # is a task that stays RUNNING for as long as the machine is
        # powered, and an operator reading "on the way" about a machine
        # that stopped moving some time ago.
        if self.navigator.failed:
            self._finish(TaskState.TASK_STATE_FAILED, self.cfg.say("could_not_finish"))
            return

        if self.navigator.arrived:
            self._laps_remaining -= 1
            if self._laps_remaining > 0:
                self.navigator.follow(self._route_for(task) or [])
                return
            self._finish(TaskState.TASK_STATE_DONE, self.cfg.say("finished"))
            return

        self._report_progress()

    def _report_progress(self) -> None:
        task = self.world.current_task
        if task is None:
            return
        # Only on meaningful change, so the feed and the wire stay quiet
        # while nothing is happening.
        progress = self.navigator.progress
        if progress - self._last_progress < 0.05:
            return
        self._last_progress = progress
        self.link.task_status(
            task_id=task.task_id,
            status=TaskState.TASK_STATE_RUNNING,
            progress=progress,
            message=self.cfg.say("running"),
            eta_sec=self._eta_sec(),
        )

    def _eta_sec(self) -> int:
        speed = self.manifest.max_speed_mps
        if speed <= 0:
            return 0
        return int(self.navigator.remaining_m / speed)

    def _finish(self, state: int, message: str) -> None:
        task = self.world.current_task
        if task is None:
            return
        self.link.task_status(
            task_id=task.task_id,
            status=state,
            progress=1.0 if state == TaskState.TASK_STATE_DONE else self.navigator.progress,
            message=message,
        )
        self.world.current_task = None
        self._last_progress = -1.0
        self.status = AssetStatus.ASSET_STATUS_STANDBY
        self.navigator.cancel()

    def _drain_battery(self, dt: float) -> None:
        drain = self.manifest.battery_drain_per_minute * (dt / 60.0)
        self.battery = max(0.0, self.battery - drain)

    # -- sensing -----------------------------------------------------------

    def _sense(self) -> None:
        """Turn what the sensors report into contract observations.

        This is where a sensor's view becomes a place in the world: the
        driver reports an offset from the machine, and the machine's own
        position turns it into a coordinate. A sensor driver that had to
        know where it was would be a sensor driver that broke when the
        machine moved.
        """
        pose = self.drivers.locomotion.pose()
        for sensor in self.drivers.sensors:
            for detection in sensor.poll():
                lat, lon = geo.offset(
                    pose.latitude_deg,
                    pose.longitude_deg,
                    detection.offset_north_m,
                    detection.offset_east_m,
                )
                entity = self.world.resolve(detection, lat, lon)
                observation = Observation(
                    observation_id=str(ULID()),
                    entity_id=entity.entity_id,
                    asset_id=self.manifest.asset_id,
                    position=Position(latitude_deg=lat, longitude_deg=lon),
                    confidence=detection.confidence,
                    entity_class=detection.entity_class,
                    narration=detection.narration,
                    timestamp=timestamp_now(),
                )
                for key, value in detection.attributes.items():
                    observation.attributes[key] = value
                self.link.observation(observation)

    # -- reporting ---------------------------------------------------------

    def _position(self) -> Position:
        pose = self.drivers.locomotion.pose()
        return Position(latitude_deg=pose.latitude_deg, longitude_deg=pose.longitude_deg)

    def _send_heartbeat(self) -> None:
        task = self.world.current_task
        self.link.heartbeat(
            asset_class=self.manifest.asset_class,
            status=self.status,
            battery_fraction=self.battery,
            position=self._position(),
            current_task_id=task.task_id if task else "",
        )

    def _send_telemetry(self) -> None:
        pose = self.drivers.locomotion.pose()
        self.link.telemetry(
            position=Position(latitude_deg=pose.latitude_deg, longitude_deg=pose.longitude_deg),
            heading_deg=pose.heading_deg,
            speed_mps=pose.speed_mps,
        )


def runtime_config(messages: dict[str, str], **overrides: Any) -> RuntimeConfig:
    return RuntimeConfig(messages=messages, **overrides)
