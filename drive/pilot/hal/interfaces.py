"""The hardware abstraction layer's driver interfaces.

Four driver kinds: locomotion, sensing, comms, and localization (the
fourth, added by ADR-0004; its provider interface lives in
localization.py, and the richer sensing seam lives in perception.py).
Everything above this file is written once and runs on every machine;
everything machine-specific lives in an implementation of one of these
protocols.

The HAL law is the reason this file is small. If code above the HAL has to
ask what kind of machine it is running on, the design has failed and the
fix belongs here rather than in a branch upstream.

Each driver also reports itself to the registry (see registry.py), because
the registry law requires that everything the HAL knows is queryable
structured data rather than something only the code knows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

# A comms driver hands (topic, payload) to whoever subscribed.
Handler = Callable[[str, bytes], None]


@dataclass(frozen=True)
class DriverInfo:
    """What a driver says about itself when the registry asks.

    Every field here ends up as structured data an operator's admin surface
    or a future integration copilot can read without running the code.
    """

    name: str
    kind: str  # "locomotion", "sensor", "comms", or "localization"
    version: str
    # What physical thing this driver speaks to, for example "simulated",
    # "zed_x", "ublox_f9p". OPEN vocabulary, like the contract's own.
    device: str
    # Free-form driver settings, for example serial port or frame rate.
    # Kept open so a new driver never needs a registry schema change.
    settings: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DriverHealth:
    """A driver's current health, sampled on demand.

    `healthy` is the machine-readable answer and `detail` is the sentence a
    person reads. The honesty law applies here too: a driver that does not
    know its own state says so rather than reporting healthy.

    `detail` comes from `pilot/data/driver_language.yaml`, never from a
    string literal in a driver. These sentences reach people, and every
    sentence that reaches a person lives in data so a deployment can change
    its words without reflashing its machines.
    """

    healthy: bool
    detail: str


@dataclass(frozen=True)
class Waypoint:
    """Somewhere to go. Altitude is optional because the ground domain has
    no use for it and the air domain will."""

    latitude_deg: float
    longitude_deg: float
    altitude_m: float | None = None


@dataclass(frozen=True)
class Pose:
    """Where the machine is and which way it is pointing."""

    latitude_deg: float
    longitude_deg: float
    heading_deg: float
    speed_mps: float
    altitude_m: float | None = None


@dataclass(frozen=True)
class Detection:
    """Something a sensor driver saw.

    Deliberately not an Observation: the contract's Observation carries
    identity and provenance that only the autonomy core can supply. A sensor
    driver reports what its hardware perceived and nothing more, so that
    swapping a camera never changes how identity works.
    """

    entity_class: str
    confidence: float
    # Where the thing is relative to the machine, in meters. The autonomy
    # core turns this into a world position using its own localization,
    # which is why a sensor driver never needs to know where it is.
    offset_north_m: float
    offset_east_m: float
    attributes: dict[str, str] = field(default_factory=dict)
    narration: str = ""


@runtime_checkable
class Driver(Protocol):
    """Common to all three kinds."""

    def info(self) -> DriverInfo: ...

    def health(self) -> DriverHealth: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


@runtime_checkable
class LocomotionDriver(Driver, Protocol):
    """Making the machine move.

    Two primitives. `set_velocity` is the continuous one a controller drives
    at rate; `goto` is the discrete one for drivers whose platform does its
    own point-to-point movement. A driver implements both; one of them may
    be built from the other.

    Nothing here says wheels. A rotor or rudder driver implements the same
    two calls, which is what makes a second body type additive.

    Units and signs, stated because getting them wrong is silent:
    `linear_mps` is metres per second, positive forward and negative in
    reverse. `angular_dps` is degrees per second of compass heading,
    positive clockwise, to match `Pose.heading_deg` and the way a manifest
    and an operator talk about direction. Callers working in a robotics
    frame where yaw is positive anticlockwise must convert.
    """

    def set_velocity(self, linear_mps: float, angular_dps: float) -> None: ...

    def goto(self, waypoint: Waypoint) -> None: ...

    def stop_moving(self) -> None: ...

    def pose(self) -> Pose:
        """The driver's own odometry: where counting its actuators says
        the machine is.

        MIGRATING SEAM (ADR-0004). "Where am I" now belongs to the
        LocalizationProvider in localization.py, and everything above the
        HAL reads estimates from it, never poses from here. Four callers
        remain, and only these: the dead-reckoning provider that wraps
        this call, the ROS bridge that publishes it as /odom,
        Nav2Navigator's route-length arithmetic, and the container
        diagnostic tool (docker/diagnose_nav2.py). All migrate to the
        provider with the Jetson bring-up. Do not add new callers.
        """
        ...


@runtime_checkable
class SensorDriver(Driver, Protocol):
    """Perceiving the world, original narrow form.

    MIGRATING SEAM (ADR-0003). Detections are one stream among several
    now: new sensor drivers implement `streams()` from perception.py and
    declare what their hardware actually provides (detections, GNSS
    fixes, frames, depth, IMU). A driver that only implements `poll()`
    keeps working through the shim in `perception.streams_of`, which
    presents it as a single detections stream. Do not write new drivers
    against poll().
    """

    def poll(self) -> list[Detection]: ...


@runtime_checkable
class CommsDriver(Driver, Protocol):
    """Reaching the platform.

    Publish, subscribe, and connection state. Version 1 ships MQTT over
    WiFi; mesh radio and satellite are later drivers behind this same
    protocol. `on_connected` lets the LINK client flush what it held while
    the link was down, which is how the disconnection law is honoured
    without the autonomy core having to think about it.
    """

    on_connected: Callable[[], None] | None

    def publish(self, topic: str, payload: bytes) -> None: ...

    def subscribe(self, topic: str, handler: Handler) -> None: ...

    @property
    def connected(self) -> bool: ...
