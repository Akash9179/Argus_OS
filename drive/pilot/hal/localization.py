"""Localization as a first-class provider (ADR-0004).

"Where am I" used to be answered by the locomotion driver, which welded
position to the thing that turns wheels. This module is the honest seam: a
LocalizationProvider produces PoseEstimates, and everything above the HAL
reads position from it and nowhere else. Which provider answers is a
manifest choice, never a code change: dead reckoning today, GNSS or visual
tracking or a fusion of them when that hardware exists.

`LocomotionDriver.pose()` remains during the migration as the odometry a
dead-reckoning provider wraps, and as the seam the ROS bridge still reads
until it too is moved over. New code reads estimates, not poses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pilot.hal.interfaces import Driver, LocomotionDriver
from pilot.hal.language import say
from pilot.hal.registry import Device

PROVIDER_VERSION = "1.0.0"


@dataclass(frozen=True)
class PoseEstimate:
    """Where the machine believes it is, and how much to believe it.

    More than a Pose on purpose: an estimate carries its source and its
    honesty. `horizontal_uncertainty_m` is one standard deviation of
    horizontal error, and None when the provider genuinely does not know,
    which dead reckoning does not. Inventing a number there would be the
    honesty law violated at the seam built to carry it.

    `source` is open vocabulary: "dead_reckoning", "gnss", "visual",
    "fused" are documented values; unknown ones pass through.
    """

    latitude_deg: float
    longitude_deg: float
    heading_deg: float
    speed_mps: float
    # Required, not defaulted: an estimate nobody signed is an estimate
    # nothing downstream can trace (law 16).
    source: str
    altitude_m: float | None = None
    horizontal_uncertainty_m: float | None = None
    healthy: bool = True


@runtime_checkable
class LocalizationProvider(Driver, Protocol):
    """The fourth driver kind. One question, answered on demand."""

    def estimate(self) -> PoseEstimate: ...


class DeadReckoningLocalization:
    """The provider every machine gets when it declares nothing better.

    Wraps the locomotion driver's own position arithmetic, which keeps
    today's behavior exactly as it was while moving the seam to where it
    belongs. It reports its uncertainty as unknown because counted wheel
    turns drift without bound and the driver has no way to measure by how
    much.
    """

    def __init__(self, locomotion: LocomotionDriver, **_ignored: object):
        self._locomotion = locomotion
        self._running = False

    def info(self):
        from pilot.hal.interfaces import DriverInfo

        return DriverInfo(
            name="dead_reckoning_localization",
            kind="localization",
            version=PROVIDER_VERSION,
            device="dead_reckoning",
            settings={},
        )

    def health(self):
        from pilot.hal.interfaces import DriverHealth

        if not self._running:
            return DriverHealth(False, say("localization_stopped"))
        return DriverHealth(True, say("localization_dead_reckoning"))

    def scan(self) -> list[Device]:
        # Dead reckoning reads no bus of its own; the wheels it counts
        # belong to the locomotion driver's scan.
        return []

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def estimate(self) -> PoseEstimate:
        pose = self._locomotion.pose()
        return PoseEstimate(
            latitude_deg=pose.latitude_deg,
            longitude_deg=pose.longitude_deg,
            heading_deg=pose.heading_deg,
            speed_mps=pose.speed_mps,
            altitude_m=pose.altitude_m,
            horizontal_uncertainty_m=None,
            source="dead_reckoning",
            healthy=self._running,
        )
