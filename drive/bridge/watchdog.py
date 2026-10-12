"""The watchdog: loss of link or operator silence stops the vehicle.

State machine (maps to the cockpit's SafetyState):
    STOPPED  - not armed. Commands are accepted but drive outputs are forced
               neutral. The resting state. Arming needs a fresh arm press
               (see below) with estop=false and throttle=0.
    DRIVING  - armed and being fed. Commands flow to the vehicle.
    LATCHED  - the feed went silent while DRIVING (or estop was pressed).
               The vehicle was safe-stopped and STAYS stopped until an
               explicit re-arm: a fresh arm press (see below) with
               estop=false and throttle=0. Re-arming is never automatic.
               No exceptions.

Arming is a rising edge, never a level. The watchdog arms only on a frame
whose arm bit is true when the previous frame it saw had arm=false. A frame
that merely continues arm=true never arms. This matters for frames queued
in a stalled socket: they still carry the arm the operator held before the
link stalled, and when they drain they must not re-arm a latch.

The detector starts every session as if arm were held. A session's first
frame therefore never arms; at least one arm=false frame must come first.
link_lost() resets it the same way, and the daemon calls it whenever the
driver's socket closes, driving or not. Every latch (estop, operator
silence, link loss) also resets it, so a stale held arm can only arm again
after it is released and pressed again. Every estop frame resets it too,
so an estop frame never counts as the release before a press. A voluntary
disarm needs no reset:
the daemon disarms only on a frame whose arm bit the detector has already
recorded. If that bit was false, it was a real release. If it was true and
the self-test was withdrawn, the detector already reads it as held.

The edge is taken on the operator's own arm bit, not on arm-and-ready. A
press made while the self-test had not passed is spent. The green light
arriving while the arm is still held is not a fresh act.

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
        # The previous arm bit this session sent. True means "treat as held":
        # a new session must release before a press counts.
        self._prev_arm = True

    @property
    def state(self) -> str:
        return self._state

    def feed(self) -> None:
        self._last_feed = self._now()

    def command(self, arm: bool, estop: bool, throttle: float, *, ready: bool) -> bool:
        """Register the operator's intent from a command frame.
        `arm` is the operator's own arm bit. `ready` is whether arming is
        permitted at all (the daemon passes the self-test verdict). It has
        no default, so a caller cannot forget it and fail open.
        Every arm, first or re-arm, needs zero throttle: the bridge does
        not trust the cockpit's neutral-stick gate.
        Returns True when drive outputs may reach the vehicle."""
        self.feed()
        pressed = arm and not self._prev_arm   # false-to-true edge only
        self._prev_arm = arm
        if estop:
            self._latch()
            return False
        if self._state == "LATCHED":
            if pressed and ready and throttle == 0.0:
                self._state = "DRIVING"      # explicit re-arm
                return True
            return False
        if self._state == "STOPPED":
            if pressed and ready and throttle == 0.0:
                self._state = "DRIVING"
            return self._state == "DRIVING"
        return True  # DRIVING: a held arm keeps it, idempotent

    def _latch(self) -> None:
        """Every latch goes through here, so the edge detector is reset the
        same way whatever the reason: the arm is treated as held."""
        self._state = "LATCHED"
        self._prev_arm = True

    def disarm(self) -> None:
        """Operator dropped arm voluntarily: back to STOPPED, no latch.
        The edge detector keeps the bit of the frame that caused this."""
        if self._state == "DRIVING":
            self._state = "STOPPED"

    def check(self) -> bool:
        """Poll from the tick thread. Returns True exactly when the dog
        trips (silence while DRIVING): caller must safe_stop() the vehicle."""
        if self._state != "DRIVING":
            return False
        if self._now() - self._last_feed > self.timeout_s:
            self._latch()
            return True
        return False

    def link_lost(self) -> bool:
        """The driver's socket died. Trip immediately if driving. Either
        way the next driver's session starts with the arm treated as held."""
        self._prev_arm = True
        if self._state == "DRIVING":
            self._latch()
            return True
        return False
