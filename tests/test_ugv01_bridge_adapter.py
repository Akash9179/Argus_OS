"""The teleop bridge's adapter for ugv-01 is a shim over Ugv01Controls.

It maps the cockpit's Command onto the controls' vocabulary and never
talks to a port itself. These tests use a recording stand-in for the
controls, so they pin the mapping, not the wire.
"""
from __future__ import annotations

import pytest

from bridge.contract import Command
from bridge.ugv01 import Ugv01Vehicle
from pilot.hal.drivers.ugv01.controls import Refused


class FakeControls:
    def __init__(self):
        self.calls: list[tuple] = []
        self.refuse: set[str] = set()
        self.snap = {
            "drive": {"firmware": "4.1.4", "connected": True, "answering": True,
                      "last_reply_age_s": 0.1, "status_raw": "D0N1"},
            "accel": {"firmware": "1.2", "connected": True, "answering": True,
                      "alive": True, "duty_commanded": 0, "duty_acked": 0,
                      "last_reply_age_s": 0.1},
            "steer": {"angle_deg": 160.0, "angle_age_s": 0.1,
                      "limits_deg": (67.0, 243.0), "target_deg": None,
                      "moving": "stop", "sense": None},
            "brake": {"angle_deg": 61.1, "limits_deg": (70.0, 170.0), "applied": False},
            "commanded": {"gear": "N", "light": "off", "indicator": "off", "speed_mode": None},
            "safe_stopped": False, "faults": [], "stop_confirmed": True,
        }

    def _rec(self, name, *a):
        if name in self.refuse:
            raise Refused("%s refused by test" % name)
        self.calls.append((name,) + a)

    def heartbeat(self): self._rec("heartbeat")
    def set_throttle(self, pct): self._rec("set_throttle", pct)
    def brake(self, action): self._rec("brake", action)
    def steer(self, direction): self._rec("steer", direction)
    def gear(self, g): self._rec("gear", g); self.snap["commanded"]["gear"] = g
    def light(self, w): self._rec("light", w); self.snap["commanded"]["light"] = w
    def indicator(self, w): self._rec("indicator", w); self.snap["commanded"]["indicator"] = w
    def horn(self): self._rec("horn")
    def safe_stop(self): self._rec("safe_stop")
    def tick(self): self._rec("tick")
    def snapshot(self): return self.snap

    def names(self):
        return [c for c in self.calls if c[0] not in ("heartbeat", "tick")]


def cmd(**kw):
    base = dict(steer=0.0, throttle=0.0, gear="N", mode="MANUAL", ignition=True,
                headlights=False, blinker="off", horn=False, record=False,
                arm=True, estop=False, brake=False)
    base.update(kw)
    return Command(**base)


@pytest.fixture
def rig():
    """A vehicle after its first frame. The first frame is the sync frame:
    it commands gear, light and indicator so the board matches the
    cockpit; everything after is edges."""
    fc = FakeControls()
    v = Ugv01Vehicle(fc)
    v.apply(cmd())
    assert fc.names() == [("gear", "N"), ("set_throttle", 0), ("light", "off"), ("indicator", "off")]
    fc.calls.clear()
    return v, fc


def test_every_frame_feeds_the_heartbeat(rig):
    v, fc = rig
    v.apply(cmd())
    v.apply(cmd())
    assert [c for c in fc.calls if c[0] == "heartbeat"] == [("heartbeat",), ("heartbeat",)]


def test_a_repeated_neutral_frame_sends_nothing_but_the_heartbeat(rig):
    v, fc = rig
    v.apply(cmd())
    assert fc.names() == []


def test_gear_maps_f_to_drive_and_only_sends_on_change(rig):
    v, fc = rig
    v.apply(cmd(gear="F"))
    v.apply(cmd(gear="F"))
    v.apply(cmd(gear="R"))
    assert fc.names() == [("gear", "D"), ("gear", "R")]


def test_a_refused_gear_change_is_not_pretended(rig):
    v, fc = rig
    fc.refuse.add("gear")
    v.apply(cmd(gear="F"))
    assert v.read().gear == "N"
    assert "gear" in v.last_refusal


def test_throttle_is_percent_and_resent_only_on_change(rig):
    v, fc = rig
    v.apply(cmd(throttle=0.4))
    v.apply(cmd(throttle=0.4))
    v.apply(cmd(throttle=0.0))
    v.apply(cmd(throttle=0.0))
    assert fc.names() == [("set_throttle", 40), ("set_throttle", 0)]


def test_steer_is_momentary_bang_bang_with_a_deadband(rig):
    v, fc = rig
    v.apply(cmd(steer=0.1))      # inside the deadband: nothing
    v.apply(cmd(steer=0.8))
    v.apply(cmd(steer=0.9))      # same direction: nothing new
    v.apply(cmd(steer=0.0))
    v.apply(cmd(steer=-1.0))
    v.apply(cmd(steer=0.0))
    assert fc.names() == [("steer", "right"), ("steer", "stop"),
                          ("steer", "left"), ("steer", "stop")]


def test_brake_applies_and_releases_on_edges(rig):
    v, fc = rig
    v.apply(cmd(brake=True))
    v.apply(cmd(brake=True))
    v.apply(cmd(brake=False))
    assert fc.names() == [("brake", "apply"), ("brake", "release")]


def test_lights_indicators_and_horn(rig):
    v, fc = rig
    v.apply(cmd(headlights=True, blinker="left"))
    v.apply(cmd(headlights=True, blinker="left", horn=True))
    v.apply(cmd(headlights=True, blinker="left", horn=True))   # held horn: one pulse
    v.apply(cmd(headlights=False, blinker="off"))
    assert fc.names() == [("light", "low"), ("indicator", "left"), ("horn",),
                          ("light", "off"), ("indicator", "off")]


def test_hazard_is_not_a_channel_this_board_has(rig):
    v, fc = rig
    v.apply(cmd(blinker="hazard"))
    assert ("indicator", "park") not in fc.names()
    assert fc.names() == []
    assert "hazard" in v.last_refusal


def test_estop_is_a_safe_stop_every_frame_it_is_held(rig):
    v, fc = rig
    v.apply(cmd(estop=True, throttle=0.5))
    v.apply(cmd(estop=True))
    assert fc.names() == [("safe_stop",), ("safe_stop",)]


def test_safe_stop_and_tick_pass_through(rig):
    v, fc = rig
    v.safe_stop()
    v.tick(0.05)
    assert ("safe_stop",) in fc.calls and ("tick",) in fc.calls


def test_telemetry_reads_the_controls_and_claims_nothing_it_does_not_know(rig):
    v, fc = rig
    v.apply(cmd(gear="F", headlights=True))
    t = v.read()
    assert t.gear == "F"
    assert t.steerAngleDeg == 5.0          # 160 minus the centre of 67..243
    assert t.ignition is True
    assert t.lights["headlights"] is True
    assert t.speedKmh == 0.0 and t.headingDeg == 0.0
    assert t.battery == {"percent": 0.0, "runtimeMin": 0.0}   # no battery source on these boards


def test_self_test_refuses_to_arm_until_the_link_loss_stop_is_proven(rig):
    v, fc = rig
    checks = {c["name"]: c for c in v.self_test()}
    assert checks["drive_board"]["ok"] is True and "4.1.4" in checks["drive_board"]["detail"]
    assert checks["accel_board"]["ok"] is True
    assert checks["steer_feedback"]["ok"] is True
    assert checks["brake_feedback"]["ok"] is True
    assert checks["faults"]["ok"] is True
    assert checks["stop_on_link_loss"]["ok"] is False
    assert "not proven" in checks["stop_on_link_loss"]["detail"]


def test_self_test_fails_when_a_board_is_silent(rig):
    v, fc = rig
    fc.snap["accel"]["answering"] = False
    fc.snap["accel"]["alive"] = False
    checks = {c["name"]: c for c in v.self_test()}
    assert checks["accel_board"]["ok"] is False
