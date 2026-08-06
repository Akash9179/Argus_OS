"""Wire contract between cockpit and bridge.

Mirrors drive/cockpit/src/contract/index.ts field for field, plus `ignition`
(carried in `aux`; the cockpit adopts it in its next pass). Unknown fields in
incoming messages are ignored, never fatal: old cockpits must keep working
against newer bridges and vice versa.

Wire messages (JSON, one object per WebSocket text frame):
  cockpit -> bridge:  {"t":"auth","password":...}
                      {"t":"cmd", ...Command}
                      {"t":"hb"}
  bridge -> cockpit:  {"t":"role","role":"DRIVER"|"SPECTATOR"}
                      {"t":"telemetry", ...Telemetry}
                      {"t":"error","reason":...}
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

PROTOCOL_VERSION = 1

GEARS = ("R", "N", "F")
BLINKERS = ("off", "left", "right", "hazard")
MODES = ("MANUAL", "AUTO")
SAFETY_STATES = ("DRIVING", "STOPPED", "LATCHED")


def clamp_unit(n: float) -> float:
    return max(0.0, min(1.0, float(n)))


def clamp_signed(n: float) -> float:
    return max(-1.0, min(1.0, float(n)))


@dataclass
class Command:
    steer: float = 0.0            # -1..1
    throttle: float = 0.0         # 0..1
    gear: str = "N"               # R | N | F
    mode: str = "MANUAL"
    ignition: bool = False
    headlights: bool = False
    blinker: str = "off"
    horn: bool = False
    record: bool = False
    arm: bool = False
    estop: bool = False

    @staticmethod
    def neutral() -> "Command":
        return Command()

    @staticmethod
    def from_wire(obj: dict[str, Any]) -> "Command":
        """Parse the cockpit's nested Command shape. Bad values clamp or
        fall back to safe defaults; they never raise past this point."""
        aux = obj.get("aux") or {}
        safety = obj.get("safety") or {}
        gear = obj.get("gear")
        blinker = aux.get("blinker")
        mode = obj.get("mode")
        return Command(
            steer=clamp_signed(_num(obj.get("steer"), 0.0)),
            throttle=clamp_unit(_num(obj.get("throttle"), 0.0)),
            gear=gear if gear in GEARS else "N",
            mode=mode if mode in MODES else "MANUAL",
            ignition=bool(aux.get("ignition", False)),
            headlights=bool(aux.get("headlights", False)),
            blinker=blinker if blinker in BLINKERS else "off",
            horn=bool(aux.get("horn", False)),
            record=bool(aux.get("record", False)),
            arm=bool(safety.get("arm", False)),
            estop=bool(safety.get("estop", False)),
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "steer": self.steer,
            "throttle": self.throttle,
            "gear": self.gear,
            "mode": self.mode,
            "aux": {
                "ignition": self.ignition,
                "headlights": self.headlights,
                "blinker": self.blinker,
                "horn": self.horn,
                "record": self.record,
            },
            "safety": {"arm": self.arm, "estop": self.estop},
        }


@dataclass
class Telemetry:
    speedKmh: float = 0.0
    gear: str = "N"
    steerAngleDeg: float = 0.0
    mode: str = "MANUAL"
    armed: bool = False
    safetyState: str = "STOPPED"  # DRIVING | STOPPED | LATCHED
    ignition: bool = False
    battery: dict = field(default_factory=lambda: {"percent": 100.0, "runtimeMin": 0.0})
    lights: dict = field(default_factory=lambda: {"headlights": False, "blinker": "off", "horn": False})
    recording: bool = False
    linkRttMs: float = 0.0
    tempC: float = 0.0
    headingDeg: float = 0.0

    def to_wire(self) -> dict[str, Any]:
        d = asdict(self)
        d["t"] = "telemetry"
        d["v"] = PROTOCOL_VERSION
        return d


def _num(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
