"""Vehicle adapters.

The daemon only ever talks to a VehicleAdapter. The mock implements the full
control set with toy physics so the cockpit, watchdog, and protocol can be
built and demonstrated with zero hardware. The real adapter for ugv-01 is
written after the hardware survey (bodies/ugv-01/README.md) and is the ONLY
place MCU specifics may live.
"""
from __future__ import annotations

import abc
import threading

from .contract import Command, Telemetry


class VehicleAdapter(abc.ABC):
    """Everything the daemon needs from a vehicle. Implementations must be
    thread-safe: apply() and read() are called from different threads."""

    @abc.abstractmethod
    def apply(self, cmd: Command) -> None:
        """Apply a full command frame."""

    @abc.abstractmethod
    def read(self) -> Telemetry:
        """Current telemetry snapshot."""

    @abc.abstractmethod
    def safe_stop(self) -> None:
        """Bring the vehicle to a safe state immediately: zero throttle,
        neutral steer. Must be idempotent and must not depend on the link."""

    @abc.abstractmethod
    def self_test(self) -> list[dict]:
        """Pre-arm checks, run when ignition comes on. Each check is
        {"name": str, "ok": bool, "detail": str}. The daemon refuses to
        arm until every check passes. Must be safe to run repeatedly and
        must never move the vehicle."""


class MockVehicle(VehicleAdapter):
    """Toy physics, honest state machine.

    Rules the mock enforces (the real vehicle will too):
      - No motion without ignition AND gear in F/R.
      - Battery drains with throttle, trickles at idle.
      - safe_stop() zeroes throttle and steer but leaves ignition/lights as
        they are: a watchdog stop is not a shutdown.
    """

    MAX_SPEED_KMH = 20.0
    STEER_RANGE_DEG = 30.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cmd = Command.neutral()
        self._speed = 0.0
        self._battery = 100.0
        self._heading = 0.0

    def apply(self, cmd: Command) -> None:
        with self._lock:
            self._cmd = cmd

    def safe_stop(self) -> None:
        with self._lock:
            c = self._cmd
            self._cmd = Command(
                steer=0.0, throttle=0.0, gear=c.gear, mode=c.mode,
                ignition=c.ignition, headlights=c.headlights,
                blinker=c.blinker, horn=False, record=c.record,
                arm=False, estop=c.estop,
            )

    def tick(self, dt: float) -> None:
        """Advance the toy physics by dt seconds. Called by the daemon's
        tick thread; call it manually in tests."""
        with self._lock:
            c = self._cmd
            moving_allowed = c.ignition and c.gear in ("F", "R") and not c.estop
            target = c.throttle * self.MAX_SPEED_KMH if moving_allowed else 0.0
            # first-order approach to target speed
            rate = 8.0 if target > self._speed else 14.0  # brakes beat engine
            step = rate * dt
            if abs(target - self._speed) <= step:
                self._speed = target
            else:
                self._speed += step if target > self._speed else -step
            if c.ignition:
                drain = 0.02 + 0.3 * c.throttle if moving_allowed else 0.02
                self._battery = max(0.0, self._battery - drain * dt)
            if self._speed > 0.05:
                sign = 1.0 if c.gear == "F" else -1.0
                self._heading = (self._heading + sign * c.steer * 40.0 * dt) % 360.0

    def self_test(self) -> list[dict]:
        with self._lock:
            battery = self._battery
        def check(name, ok, detail):
            return {"name": name, "ok": bool(ok), "detail": detail}
        return [
            check("mcu_link", True, "serial echo ok (mock)"),
            check("battery", battery > 10.0, f"{battery:.0f}%"),
            check("steering", True, "sweep ok (mock)"),
            check("throttle", True, "zero verified (mock)"),
            check("estop_circuit", True, "loop closed (mock)"),
            check("watchdog", True, "armed"),
        ]

    def read(self) -> Telemetry:
        with self._lock:
            c = self._cmd
            runtime = (self._battery / 100.0) * 90.0  # 90 min on a full charge
            return Telemetry(
                speedKmh=round(self._speed, 2),
                gear=c.gear,
                steerAngleDeg=round(c.steer * self.STEER_RANGE_DEG, 1),
                mode=c.mode,
                armed=c.arm,
                safetyState="STOPPED",  # daemon overwrites from the watchdog
                ignition=c.ignition,
                battery={"percent": round(self._battery, 1), "runtimeMin": round(runtime)},
                lights={"headlights": c.headlights, "blinker": c.blinker, "horn": c.horn},
                recording=c.record,
                tempC=42.0,
                headingDeg=round(self._heading, 1),
            )
