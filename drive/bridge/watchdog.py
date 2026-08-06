"""The watchdog: loss of link or operator silence stops the vehicle.

State machine (maps to the cockpit's SafetyState):
    STOPPED  - not armed. Commands are accepted but drive outputs are forced
               neutral. The resting state.
    DRIVING  - armed and being fed. Commands flow to the vehicle.
    LATCHED  - the feed went silent while DRIVING (or estop was pressed).
               The vehicle was safe-stopped and STAYS stopped until an
               explicit re-arm: a command frame with arm=true, estop=false,
               and throttle=0. Re-arming is never automatic. No exceptions.

The daemon feeds the watchdog on every valid command frame and heartbeat.
"""
from __future__ import annotations

import time


class Watchdog:
    def __init__(self, timeout_s: float = 0.7, now=time.monotonic) -> None:
        self.timeout_s = timeout_s
        self._now = now
        self._state = "STOPPED"
        self._last_feed = self._now()

    @property
    def state(self) -> str:
        return self._state

    def feed(self) -> None:
        self._last_feed = self._now()

    def command(self, arm: bool, estop: bool, throttle: float) -> bool:
        """Register the operator's intent from a command frame.
        Returns True when drive outputs may reach the vehicle."""
        self.feed()
        if estop:
            self._state = "LATCHED"
            return False
        if self._state == "LATCHED":
            if arm and throttle == 0.0:
                self._state = "DRIVING"      # explicit re-arm
                return True
            return False
        if self._state == "STOPPED":
            if arm:
                self._state = "DRIVING"
            return self._state == "DRIVING"
        return True  # DRIVING

    def disarm(self) -> None:
        """Operator dropped arm voluntarily: back to STOPPED, no latch."""
        if self._state == "DRIVING":
            self._state = "STOPPED"

    def check(self) -> bool:
        """Poll from the tick thread. Returns True exactly when the dog
        trips (silence while DRIVING): caller must safe_stop() the vehicle."""
        if self._state != "DRIVING":
            return False
        if self._now() - self._last_feed > self.timeout_s:
            self._state = "LATCHED"
            return True
        return False

    def link_lost(self) -> bool:
        """The driver's socket died. Trip immediately if driving."""
        if self._state == "DRIVING":
            self._state = "LATCHED"
            return True
        return False
