"""The perception stream seam (ADR-0003).

The original sensor interface could carry exactly one thing across the HAL:
a finished Detection. That forced the detector inside every camera driver,
left navigation's costmaps unreachable, and gave localization nothing to
fuse. This module is the replacement seam: a sensor provides typed streams,
declares which kinds it has, and nothing above the HAL learns a device name.

Stream kinds are OPEN vocabulary, like the contract's own: "detections",
"gnss", "imu", "frames", "depth" are the kinds this build defines samples
for, and a newer driver may declare a kind this build has never heard of.
A consumer asks for the kinds it understands and ignores the rest; an
unknown kind is never an error.

The old `SensorDriver.poll()` keeps working through `streams_of`, which
wraps a poll-only driver as a detections stream. That shim is the migration
path, not the destination: new drivers implement `streams()` directly.

High-rate data stays on this local seam. Nothing here goes onto LINK; the
wire carries semantic observations only, exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pilot.hal.interfaces import Detection, SensorDriver

# The kinds this build ships sample types for. A driver may declare others.
KNOWN_STREAM_KINDS = ("detections", "gnss", "imu", "frames", "depth")

# The fix values that actually hold a fix. Drivers gate the claim "has a
# fix" on this one tuple; any other value is preserved and passed through
# without being claimed or denied.
GNSS_FIX_HOLDING_VALUES = ("2d", "3d", "rtk_float", "rtk_fixed")


@dataclass(frozen=True)
class GnssSample:
    """One fix from a satellite receiver.

    The one sensor allowed to speak in world coordinates, because knowing
    where it is on Earth is the thing the hardware actually measures.
    `fix` is open vocabulary: "none", "2d", "3d", "rtk_float", "rtk_fixed"
    are the documented values and an unknown one passes through.
    """

    timestamp_s: float
    latitude_deg: float
    longitude_deg: float
    altitude_m: float | None = None
    horizontal_accuracy_m: float | None = None
    fix: str = "3d"
    satellites: int | None = None


@dataclass(frozen=True)
class ImuSample:
    """One inertial reading. Axes follow the vehicle frame documented on
    the locomotion interface: x forward, y right, z down."""

    timestamp_s: float
    accel_mps2: tuple[float, float, float]
    gyro_dps: tuple[float, float, float]


@dataclass(frozen=True)
class FrameSample:
    """One camera frame, by reference.

    The bytes stay wherever the driver put them; this seam carries the
    description and the handle. Pixels never travel through the autonomy
    loop and never reach LINK.
    """

    timestamp_s: float
    width: int
    height: int
    encoding: str  # open vocabulary, for example "bgr8", "jpeg"
    data: bytes = b""
    intrinsics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DepthSample:
    """One depth image, same conventions as FrameSample. Depth in meters
    encoded per `encoding`."""

    timestamp_s: float
    width: int
    height: int
    encoding: str
    data: bytes = b""
    min_range_m: float | None = None
    max_range_m: float | None = None


@runtime_checkable
class SensorStream(Protocol):
    """One typed stream from one sensor. Pull-based, like the seam it
    replaces: `read` returns everything since the last call and never
    blocks."""

    @property
    def kind(self) -> str: ...

    def read(self) -> list[Any]: ...


@runtime_checkable
class PerceptionSensor(Protocol):
    """A sensor driver that provides typed streams.

    A driver implements the streams its hardware actually has; nothing
    requires every kind. Capabilities are discoverable here and mirrored
    into the registry, so "what can this sensor do" is a query, not a
    code read (law 10).
    """

    def streams(self) -> dict[str, SensorStream]: ...


class _PolledDetections:
    """The compatibility shim: a poll()-only driver seen as a stream."""

    kind = "detections"

    def __init__(self, driver: SensorDriver):
        self._driver = driver

    def read(self) -> list[Detection]:
        return self._driver.poll()


class ListStream:
    """A stream a driver fills and a consumer drains. The simplest correct
    implementation of the protocol; simulated and buffered real drivers
    both use it."""

    def __init__(self, kind: str):
        self.kind = kind
        self._pending: list[Any] = []

    def push(self, sample: Any) -> None:
        self._pending.append(sample)

    def read(self) -> list[Any]:
        out, self._pending = self._pending, []
        return out


def streams_of(sensor: Any) -> dict[str, SensorStream]:
    """Every stream a sensor provides, whichever interface it speaks.

    New-style drivers answer for themselves. A poll()-only driver becomes a
    single detections stream, so every existing driver keeps working while
    the migration runs.
    """
    provide = getattr(sensor, "streams", None)
    if provide is not None:
        return dict(provide())
    return {"detections": _PolledDetections(sensor)}


def stream_kinds(sensor: Any) -> list[str]:
    """The declared kinds, for the registry and anything else that asks."""
    return sorted(streams_of(sensor))
