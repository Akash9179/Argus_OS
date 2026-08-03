"""The simulated driver set.

Three drivers that implement the HAL interfaces without any hardware. They
exist so that everything above the HAL can be built and proven before the
steel arrives, and they stay afterwards: a machine whose drivers can be
swapped for simulated ones is a machine that can be tested.

These are drivers, not a simulator. They pretend to be a motor controller,
a camera, and a radio. They do not pretend to be a vehicle, because the
vehicle is the autonomy core above them and that part is real.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from pilot import geo
from pilot.hal.interfaces import (
    Detection,
    DriverHealth,
    DriverInfo,
    Handler,
    Pose,
    Waypoint,
)
from pilot.hal.language import say
from pilot.hal.loader import register_driver
from pilot.hal.manifest import Manifest
from pilot.hal.registry import Device

log = logging.getLogger(__name__)

DRIVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Locomotion
# ---------------------------------------------------------------------------


class SimulatedLocomotion:
    """A motor controller that moves numbers instead of wheels.

    It honours the manifest's speed limit the way a real controller honours
    what its hardware can do: asked to exceed it, it clamps and says so
    through the registry rather than silently obeying. That clamp is what
    makes swapping a manifest change behaviour with no code change.
    """

    def __init__(
        self,
        manifest: Manifest,
        start_latitude_deg: float = 0.0,
        start_longitude_deg: float = 0.0,
        **_ignored: Any,
    ):
        self._max_speed = manifest.max_speed_mps
        self._lat = float(start_latitude_deg)
        self._lon = float(start_longitude_deg)
        self._heading = 0.0
        self._commanded_mps = 0.0
        self._angular_dps = 0.0
        self._target: Waypoint | None = None
        self._running = False
        self._clamped = False
        self._last_tick = time.monotonic()
        self._lock = threading.Lock()

    # -- driver ------------------------------------------------------------

    def info(self) -> DriverInfo:
        return DriverInfo(
            name="simulated_locomotion",
            kind="locomotion",
            version=DRIVER_VERSION,
            device="simulated",
            settings={"max_speed_mps": f"{self._max_speed}"},
        )

    def health(self) -> DriverHealth:
        if not self._running:
            return DriverHealth(False, say("locomotion_stopped"))
        if self._clamped:
            return DriverHealth(True, say("locomotion_clamped", limit=self._max_speed))
        return DriverHealth(True, say("locomotion_running"))

    def scan(self) -> list[Device]:
        return [
            Device(
                bus="simulated",
                identifier="motor-controller-0",
                description="simulated motor controller",
                present=True,
            )
        ]

    def start(self) -> None:
        self._running = True
        self._last_tick = time.monotonic()

    def stop(self) -> None:
        self._running = False
        self._commanded_mps = 0.0

    # -- locomotion --------------------------------------------------------

    def set_velocity(self, linear_mps: float, angular_dps: float) -> None:
        with self._lock:
            self._clamped = abs(linear_mps) > self._max_speed
            capped = max(-self._max_speed, min(self._max_speed, linear_mps))
            self._commanded_mps = capped
            self._angular_dps = angular_dps
            self._target = None

    def goto(self, waypoint: Waypoint) -> None:
        """Point-to-point movement, built from the continuous primitive.

        A platform that does its own point-to-point navigation would
        instead hand the waypoint down and leave set_velocity unused. Both
        shapes are legal, which is why the interface carries both.
        """
        with self._lock:
            self._target = waypoint
            self._commanded_mps = self._max_speed
            self._clamped = False

    def stop_moving(self) -> None:
        with self._lock:
            self._commanded_mps = 0.0
            self._angular_dps = 0.0
            self._target = None

    def pose(self) -> Pose:
        with self._lock:
            return Pose(
                latitude_deg=self._lat,
                longitude_deg=self._lon,
                heading_deg=self._heading,
                speed_mps=abs(self._commanded_mps) if self._moving() else 0.0,
            )

    # -- the part a real driver gets from hardware --------------------------

    def tick(self, dt: float | None = None) -> None:
        """Advance dead reckoning.

        A real driver has nothing like this: its wheels move and its
        localization reports where they moved to. Here the autonomy core's
        loop drives it, which keeps the arithmetic in the driver where a
        real one would keep it too.
        """
        now = time.monotonic()
        if dt is None:
            dt = now - self._last_tick
        self._last_tick = now
        if not self._running or dt <= 0:
            return

        with self._lock:
            self._heading = (self._heading + self._angular_dps * dt) % 360.0
            if not self._moving():
                return
            # Signed, because a negative command means reverse and a
            # machine that drove forward when told to back up would be a
            # machine that ran away from every goal a planner asked it to
            # reach by reversing. Distance toward a goto target is the
            # magnitude; direction of travel along a heading is not.
            travel = self._commanded_mps * dt
            step = abs(travel)
            if self._target is not None:
                remaining = geo.distance_m(
                    self._lat, self._lon, self._target.latitude_deg, self._target.longitude_deg
                )
                if remaining <= step or remaining == 0.0:
                    self._lat = self._target.latitude_deg
                    self._lon = self._target.longitude_deg
                    self._commanded_mps = 0.0
                    self._target = None
                    return
                self._heading = geo.bearing_deg(
                    self._lat, self._lon, self._target.latitude_deg, self._target.longitude_deg
                )
                self._lat, self._lon = geo.step_toward(
                    self._lat,
                    self._lon,
                    self._target.latitude_deg,
                    self._target.longitude_deg,
                    step,
                )
            else:
                self._lat, self._lon = geo.offset(
                    self._lat,
                    self._lon,
                    travel * _cos_deg(self._heading),
                    travel * _sin_deg(self._heading),
                )

    def _moving(self) -> bool:
        return self._running and abs(self._commanded_mps) > 0.0

    @property
    def arrived(self) -> bool:
        """True once a goto has been reached and movement has stopped."""
        with self._lock:
            return self._target is None and self._commanded_mps == 0.0


# ---------------------------------------------------------------------------
# Sensing
# ---------------------------------------------------------------------------


@dataclass
class ScriptedSighting:
    """Something the simulated camera will report, and when."""

    after_seconds: float
    entity_class: str
    confidence: float
    offset_north_m: float = 0.0
    offset_east_m: float = 0.0
    narration: str = ""
    attributes: dict[str, str] | None = None
    repeat_every_seconds: float = 0.0
    count: int = 1

    sent: int = 0
    next_at: float = 0.0


class SimulatedCamera:
    """A camera that sees what a script tells it to see.

    It reports offsets from the machine, never world positions, because a
    real camera does not know where it is. Turning an offset into a place on
    the map is the autonomy core's job, and keeping that split here is what
    lets a real ZED driver replace this one without touching anything above.
    """

    def __init__(self, manifest: Manifest, sightings: list[Any] | None = None, **_ignored: Any):
        self._name = "simulated_camera"
        self._running = False
        self._started_at = 0.0
        self._sightings: list[ScriptedSighting] = []
        for entry in sightings or []:
            if isinstance(entry, ScriptedSighting):
                self._sightings.append(entry)
            elif isinstance(entry, dict):
                self._sightings.append(ScriptedSighting(**entry))

    def info(self) -> DriverInfo:
        return DriverInfo(
            name=self._name,
            kind="sensor",
            version=DRIVER_VERSION,
            device="simulated",
            settings={"scripted_sightings": str(len(self._sightings))},
        )

    def health(self) -> DriverHealth:
        if not self._running:
            return DriverHealth(False, say("camera_stopped"))
        return DriverHealth(True, say("camera_running"))

    def scan(self) -> list[Device]:
        return [
            Device(
                bus="simulated",
                identifier="camera-0",
                description="simulated stereo camera",
                present=True,
            )
        ]

    def start(self) -> None:
        self._running = True
        self._started_at = time.monotonic()
        for sighting in self._sightings:
            sighting.next_at = sighting.after_seconds
            sighting.sent = 0

    def stop(self) -> None:
        self._running = False

    def poll(self) -> list[Detection]:
        if not self._running:
            return []
        elapsed = time.monotonic() - self._started_at
        found: list[Detection] = []
        for sighting in self._sightings:
            if sighting.sent >= sighting.count or elapsed < sighting.next_at:
                continue
            found.append(
                Detection(
                    entity_class=sighting.entity_class,
                    confidence=sighting.confidence,
                    offset_north_m=sighting.offset_north_m,
                    offset_east_m=sighting.offset_east_m,
                    attributes=dict(sighting.attributes or {}),
                    narration=sighting.narration,
                )
            )
            sighting.sent += 1
            sighting.next_at = elapsed + (sighting.repeat_every_seconds or 1e9)
        return found


# ---------------------------------------------------------------------------
# Comms
# ---------------------------------------------------------------------------


class SimulatedComms:
    """A radio with nothing on the other end.

    Useful on its own for a machine that has genuinely lost contact, and
    the base for the in-process driver a test uses to wire a machine
    straight to a server.
    """

    def __init__(self, manifest: Manifest, **_ignored: Any):
        self._up = False
        self._handlers: dict[str, Handler] = {}
        self.on_connected: Callable[[], None] | None = None

    def info(self) -> DriverInfo:
        return DriverInfo(
            name="simulated_comms",
            kind="comms",
            version=DRIVER_VERSION,
            device="simulated",
            settings={},
        )

    def health(self) -> DriverHealth:
        # Not being connected is not a fault. The disconnection law says a
        # machine alone is working normally, so this reports honestly
        # without calling it unhealthy.
        return DriverHealth(True, say("link_up" if self._up else "link_down"))

    def scan(self) -> list[Device]:
        return [
            Device(
                bus="simulated",
                identifier="radio-0",
                description="simulated radio",
                present=True,
            )
        ]

    @property
    def connected(self) -> bool:
        return self._up

    def publish(self, topic: str, payload: bytes) -> None:
        return

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic] = handler

    def start(self) -> None:
        self._up = True
        if self.on_connected:
            self.on_connected()

    def stop(self) -> None:
        self._up = False

    def drop(self) -> None:
        """Lose the link without stopping the machine."""
        self._up = False

    def restore(self) -> None:
        self._up = True
        if self.on_connected:
            self.on_connected()


class DirectComms(SimulatedComms):
    """An in-process comms driver.

    Wraps anything exposing publish and subscribe, which is how a whole
    machine, server, and application loop run inside one test with no
    broker. That is why the loop guarding every change needs no
    infrastructure to run.

    It is a real driver rather than a test double: it implements the comms
    interface completely, and a machine running it cannot tell it apart
    from a radio.
    """

    def __init__(self, manifest: Manifest, bus: Any = None, **_ignored: Any):
        super().__init__(manifest)
        self._bus = bus

    def info(self) -> DriverInfo:
        return DriverInfo(
            name="direct_comms",
            kind="comms",
            version=DRIVER_VERSION,
            device="in_process",
            settings={},
        )

    def publish(self, topic: str, payload: bytes) -> None:
        if self._up and self._bus is not None:
            self._bus.publish(topic, payload)

    def subscribe(self, topic: str, handler: Handler) -> None:
        super().subscribe(topic, handler)
        if self._bus is not None:
            self._bus.subscribe(topic, handler)


def _cos_deg(deg: float) -> float:
    return math.cos(math.radians(deg))


def _sin_deg(deg: float) -> float:
    return math.sin(math.radians(deg))


register_driver("simulated_locomotion", SimulatedLocomotion)
register_driver("simulated_camera", SimulatedCamera)
register_driver("simulated_comms", SimulatedComms)
register_driver("direct_comms", DirectComms)
