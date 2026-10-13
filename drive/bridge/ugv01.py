"""The teleop bridge's adapter for ugv-01: a shim over Ugv01Controls.

Per ADR-0009 the hardware is driven from exactly one place,
`pilot.hal.drivers.ugv01.controls`. This class only translates the
cockpit's Command into that vocabulary, on edges, and reads telemetry
back from its snapshot. It opens no port and knows no frame.

Mapping, and what the cockpit's contract cannot yet say:
  steer -1..1      momentary left/right/stop, bang-bang, deadband 0.3.
                   Closed-loop steer_to() waits for the bench to tell us
                   which way the angle reading grows.
  throttle 0..1    duty percent, sent on change; the controls cap it.
  gear F/N/R       D/N/R, sent on change; refused unless duty is zero.
  aux.brake        apply on rising edge, release on falling edge.
  aux.headlights   low beam on or off. The board's ring and high beams
                   have no cockpit control yet.
  aux.blinker      left, right, off. 'hazard' is not a channel this
                   board has and is refused, not approximated.
  aux.horn         one 0.5 s pulse per rising edge.
  safety.estop     safe_stop() on every frame it is held.

Telemetry it cannot earn is reported as zero and flagged false in the
`measured` map so the cockpit can show "no reading" instead of a number:
speed (no speed feedback on either board), heading, temperature, battery
(the pack is on BLE in the team's stack, not on these boards), and gear
and ignition, which are commanded state, not measured.
"""
from __future__ import annotations

import threading

from .contract import Command, Telemetry
from .vehicle import VehicleAdapter
from pilot.hal.drivers.ugv01.controls import Refused

STEER_DEADBAND = 0.3
_GEAR_TO_BOARD = {"F": "D", "N": "N", "R": "R"}
_GEAR_FROM_BOARD = {"D": "F", "N": "N", "R": "R"}


class Ugv01Vehicle(VehicleAdapter):
    def __init__(self, controls) -> None:
        self._c = controls
        self._lock = threading.Lock()
        self._last = Command.neutral()
        self._gear_sent: str | None = None
        self._duty_sent: int | None = None
        self._steer_sent: str | None = None     # unknown until the sync frame sends a stop
        self._light_sent: str | None = None
        self._ind_sent: str | None = None
        self._brake_held = False
        self._horn_held = False
        self.last_refusal: str = ""

    # ------------------------------------------------------------- commands

    def apply(self, cmd: Command) -> None:
        with self._lock:
            self._c.heartbeat()
            self._last = cmd
            if cmd.estop:
                self._c.safe_stop()
                self._duty_sent = 0
                self._steer_sent: str | None = None     # unknown until the sync frame sends a stop
                self._brake_held = True
                return
            self._try("gear", self._gear, cmd)
            self._try("brake", self._brake, cmd)
            self._try("throttle", self._throttle, cmd)
            self._try("steer", self._steer, cmd)
            self._try("light", self._light, cmd)
            self._try("indicator", self._indicator, cmd)
            self._try("horn", self._horn, cmd)

    def _try(self, what: str, fn, cmd: Command) -> None:
        try:
            fn(cmd)
        except Refused as e:
            self.last_refusal = "%s: %s" % (what, e)

    def _gear(self, cmd: Command) -> None:
        g = _GEAR_TO_BOARD[cmd.gear]
        if g != self._gear_sent:
            self._c.gear(g)
            self._gear_sent = g

    def _brake(self, cmd: Command) -> None:
        if cmd.brake and not self._brake_held:
            self._c.brake("apply")
            self._brake_held = True
            self._duty_sent = 0
        elif not cmd.brake and self._brake_held:
            self._c.brake("release")
            self._brake_held = False

    def _throttle(self, cmd: Command) -> None:
        pct = int(round(cmd.throttle * 100))
        if pct != self._duty_sent:
            self._c.set_throttle(pct)
            self._duty_sent = pct

    def _steer(self, cmd: Command) -> None:
        want = "right" if cmd.steer > STEER_DEADBAND else \
               "left" if cmd.steer < -STEER_DEADBAND else "stop"
        if want != self._steer_sent:
            self._c.steer(want)
            self._steer_sent = want

    def _light(self, cmd: Command) -> None:
        want = "low" if cmd.headlights else "off"
        if want != self._light_sent:
            self._c.light(want)
            self._light_sent = want

    def _indicator(self, cmd: Command) -> None:
        if cmd.blinker == "hazard":
            raise Refused("hazard is not a channel this board has")
        want = cmd.blinker if cmd.blinker in ("left", "right") else "off"
        if want != self._ind_sent:
            self._c.indicator(want)
            self._ind_sent = want

    def _horn(self, cmd: Command) -> None:
        if cmd.horn and not self._horn_held:
            self._c.horn()
        self._horn_held = cmd.horn

    # ------------------------------------------------------------- the rest

    def safe_stop(self) -> None:
        with self._lock:
            self._c.safe_stop()
            self._duty_sent = 0
            self._steer_sent: str | None = None     # unknown until the sync frame sends a stop
            self._brake_held = True

    def tick(self, dt: float) -> None:
        self._c.tick()

    def self_test(self) -> list[dict]:
        s = self._c.snapshot()
        def check(name, ok, detail):
            return {"name": name, "ok": bool(ok), "detail": detail}
        d, a = s["drive"], s["accel"]
        steer, brake = s["steer"], s["brake"]
        return [
            check("drive_board", d["connected"] and d["answering"] and d["firmware"],
                  "steering and brake controller answering, software %s" % d["firmware"]
                  if d["firmware"] else "steering and brake controller not answering"),
            check("accel_board", a["connected"] and a["answering"] and a["alive"],
                  "throttle board answering, software %s, throttle confirmed at zero" % a["firmware"]
                  if a["alive"] else "throttle board has not confirmed zero throttle"),
            check("steer_feedback", steer["angle_deg"] is not None and steer["limits_deg"],
                  "steering reads %s degrees, travel %s to %s" % (
                      steer["angle_deg"], *(steer["limits_deg"] or ("?", "?")))),
            check("brake_feedback", brake["angle_deg"] is not None,
                  "brake reads %s degrees" % brake["angle_deg"]),
            check("faults", not s["faults"], "; ".join(s["faults"]) or "no faults"),
            check("stop_on_link_loss", False,
                  "not proven: the vehicle has not shown it stops when the link is lost"),
        ]

    def read(self) -> Telemetry:
        s = self._c.snapshot()
        with self._lock:
            cmd = self._last
        angle = s["steer"]["angle_deg"]
        limits = s["steer"]["limits_deg"]
        if angle is None:
            steer_deg = 0.0
        elif limits:
            steer_deg = round(angle - (limits[0] + limits[1]) / 2.0, 1)
        else:
            steer_deg = round(angle, 1)
        board_gear = s["commanded"]["gear"]
        return Telemetry(
            measured={"speedKmh": False, "steerAngleDeg": angle is not None,
                      "battery": False, "tempC": False, "headingDeg": False,
                      "gear": False, "ignition": False},
            speedKmh=0.0,
            gear=_GEAR_FROM_BOARD.get(board_gear, "N"),
            steerAngleDeg=steer_deg,
            mode=cmd.mode,
            armed=False,                      # the daemon overwrites from the watchdog
            safetyState="STOPPED",            # same
            ignition=cmd.ignition,
            battery={"percent": 0.0, "runtimeMin": 0.0},
            lights={"headlights": s["commanded"]["light"] == "low",
                    "blinker": s["commanded"]["indicator"] if s["commanded"]["indicator"] in ("left", "right") else "off",
                    "horn": cmd.horn},
            recording=cmd.record,
            tempC=0.0,
            headingDeg=0.0,
        )
