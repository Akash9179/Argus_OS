"""Getting from here to there.

The navigator turns a route into commands for a locomotion driver. It is
the layer Nav2 occupies on the real machine: it plans and controls, and it
speaks to the platform only through the locomotion interface.

Two implementations, one interface. `DirectNavigator` drives waypoints
straight at the locomotion driver and is what runs in tests and anywhere a
planner would be overkill. `Nav2Navigator` (see nav2.py) hands the same
route to a real Nav2 stack. The autonomy core cannot tell which it has,
which is the point: choosing a planner is not an architecture change.

Nothing here knows about wheels, rotors, or the shape of the machine. Speed
limits and turn constraints come from the manifest, and the driver clamps
anything it cannot honour.
"""

from __future__ import annotations

import logging
from typing import Protocol

from pilot import geo
from pilot.hal.interfaces import LocomotionDriver, Waypoint

log = logging.getLogger(__name__)

# How close counts as arrived, in meters.
ARRIVAL_TOLERANCE_M = 2.0


class Navigator(Protocol):
    """What the autonomy core needs from any planner."""

    def follow(self, route: list[Waypoint]) -> None:
        """Begin following a route. Replaces whatever was being followed."""
        ...

    def cancel(self) -> None: ...

    def step(self, dt: float) -> None:
        """Advance one control cycle."""
        ...

    @property
    def arrived(self) -> bool: ...

    @property
    def failed(self) -> bool:
        """True when the route was abandoned and will not be finished.

        Distinct from "not arrived". A navigator that has given up must say
        so, because the alternative is a task that stays RUNNING forever
        and an operator who reads "on the way" about a machine that has
        stopped. Silence is the failure mode worth designing against.
        """
        ...

    @property
    def progress(self) -> float:
        """How far along the route, 0.0 to 1.0."""
        ...

    @property
    def remaining_m(self) -> float: ...


class DirectNavigator:
    """Follows a route by pointing the machine at each waypoint in turn."""

    def __init__(self, locomotion: LocomotionDriver):
        self._locomotion = locomotion
        self._route: list[Waypoint] = []
        self._index = 0
        self._total_m = 0.0
        self._done_m = 0.0

    def follow(self, route: list[Waypoint]) -> None:
        self._route = list(route)
        self._index = 0
        self._done_m = 0.0
        self._total_m = self._length(self._route)
        if self._route:
            self._locomotion.goto(self._route[0])

    def cancel(self) -> None:
        self._route = []
        self._index = 0
        self._locomotion.stop_moving()

    def step(self, dt: float) -> None:
        if not self._route or self._index >= len(self._route):
            return

        before = self._locomotion.pose()
        # A driver that dead-reckons needs its clock advanced; one attached
        # to real hardware moves on its own and has no tick.
        tick = getattr(self._locomotion, "tick", None)
        if tick is not None:
            tick(dt)
        after = self._locomotion.pose()

        self._done_m += geo.distance_m(
            before.latitude_deg, before.longitude_deg, after.latitude_deg, after.longitude_deg
        )

        target = self._route[self._index]
        remaining = geo.distance_m(
            after.latitude_deg, after.longitude_deg, target.latitude_deg, target.longitude_deg
        )
        if remaining <= ARRIVAL_TOLERANCE_M:
            self._index += 1
            if self._index < len(self._route):
                self._locomotion.goto(self._route[self._index])
            else:
                self._locomotion.stop_moving()

    @property
    def arrived(self) -> bool:
        return bool(self._route) and self._index >= len(self._route)

    @property
    def failed(self) -> bool:
        # Following waypoints in a straight line has no way to give up:
        # there is nothing to be blocked by. A driver that stops responding
        # shows up as a machine that stops sending heartbeats, which the
        # world model already notices.
        return False

    @property
    def progress(self) -> float:
        if self._total_m <= 0:
            return 1.0
        return max(0.0, min(1.0, self._done_m / self._total_m))

    @property
    def remaining_m(self) -> float:
        return max(0.0, self._total_m - self._done_m)

    def _length(self, route: list[Waypoint]) -> float:
        if not route:
            return 0.0
        pose = self._locomotion.pose()
        total = 0.0
        lat, lon = pose.latitude_deg, pose.longitude_deg
        for waypoint in route:
            total += geo.distance_m(lat, lon, waypoint.latitude_deg, waypoint.longitude_deg)
            lat, lon = waypoint.latitude_deg, waypoint.longitude_deg
        return total
