"""The bridge over the real controls over the simulated boards (4.1.6,
AC 1.4): after a link-loss stop, a fresh arm must let the steering move
again. 5 Nov 2026, found on the jack: the controls' stop latch was never
lifted, so the cockpit read DRIVING while every move was refused."""
import importlib.util
import pathlib
import json
import time

from bridge.contract import Command
from bridge.daemon import BridgeDaemon, _Client
from bridge.identity import Operator, OperatorDirectory
from bridge.ugv01 import Ugv01Vehicle
from pilot.hal.drivers.ugv01.controls import Ugv01Controls

SIM = pathlib.Path(__file__).resolve().parents[1] / "bodies/ugv-01/bench-logs/2026-10-14/simboards.py"


def _sim():
    spec = importlib.util.spec_from_file_location("simboards", SIM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(**kw):
    base = dict(steer=0.0, throttle=0.0, gear="F", mode="MANUAL", ignition=True,
                headlights=False, blinker="off", horn=False, record=False,
                arm=True, estop=False, brake=False)
    base.update(kw)
    w = Command(**base).to_wire()
    w["t"] = "cmd"
    return w


def test_a_fresh_arm_after_a_link_loss_stop_steers_again(tmp_path):
    sim = _sim()
    boards = sim.make_boards()
    c = Ugv01Controls(drive_port=sim.SimPort(boards["drive"]), accel_port=sim.SimPort(boards["accel"]),
                      steer_sense="left_increases", max_duty=20)
    c.start()
    v = Ugv01Vehicle(c)
    d = BridgeDaemon(v, operators=OperatorDirectory({"pw": Operator("op", "Op")}),
                     host="127.0.0.1", port=0, log_path=tmp_path / "s.jsonl",
                     waive=("stop_on_link_loss",))
    cl = _Client(None, ("t", 0), Operator("op", "Op"))
    d._driver = cl
    try:
        for _ in range(10):
            c.tick(); time.sleep(0.05)
        d._handle(cl, _frame(arm=False))
        d._handle(cl, _frame(arm=True))
        assert d.watchdog.state == "DRIVING"

        v.safe_stop()                                   # the bridge's link-loss stop
        d.watchdog._latch()
        assert c.snapshot()["safe_stopped"] is True

        d._handle(cl, _frame(arm=False))
        d._handle(cl, _frame(arm=True))                 # the operator's fresh arm
        assert d.watchdog.state == "DRIVING"
        assert c.snapshot()["safe_stopped"] is False

        for _ in range(6):                              # let polls land after the clear
            c.tick(); time.sleep(0.05)
        v.last_refusal = ""                             # refusals from the latched frames are history
        d._handle(cl, _frame(steer=1.0))
        assert v.last_refusal == "", v.last_refusal
        assert c.snapshot()["steer"]["moving"] == "right"
    finally:
        c.close()


def test_after_a_fresh_start_and_an_arm_the_throttle_reaches_the_board_capped(tmp_path):
    """5 Nov 2026 on the jack: the cockpit read 100 percent and the wheels
    did not turn. After a fresh bridge start no brake release ever went out,
    and the controls refuse throttle until one is acknowledged."""
    sim = _sim()
    boards = sim.make_boards()
    c = Ugv01Controls(drive_port=sim.SimPort(boards["drive"]), accel_port=sim.SimPort(boards["accel"]),
                      steer_sense="left_increases", max_duty=20)
    c.start()
    v = Ugv01Vehicle(c)
    d = BridgeDaemon(v, operators=OperatorDirectory({"pw": Operator("op", "Op")}),
                     host="127.0.0.1", port=0, log_path=tmp_path / "s.jsonl",
                     waive=("stop_on_link_loss",))
    cl = _Client(None, ("t", 0), Operator("op", "Op"))
    d._driver = cl
    try:
        for _ in range(10):
            c.tick(); time.sleep(0.05)
        d._handle(cl, _frame(arm=False))
        d._handle(cl, _frame(arm=True))
        assert d.watchdog.state == "DRIVING"
        for _ in range(6):                              # the release frame and its answer
            d._handle(cl, _frame(arm=True)); c.tick(); time.sleep(0.05)
        v.last_refusal = ""
        for _ in range(4):
            d._handle(cl, _frame(arm=True, throttle=1.0)); c.tick(); time.sleep(0.05)
        assert v.last_refusal == "", v.last_refusal
        assert boards["accel"].duty == 20
    finally:
        c.close()


def _rig_brake_absent(tmp_path):
    sim = _sim()
    boards = sim.make_boards()
    boards["drive"].brake = 174.0                       # the reading on the jack; brake disconnected
    drive_port = sim.SimPort(boards["drive"])
    sent = []
    real_write = drive_port.write
    def write(data):
        sent.append(data)
        return real_write(data)
    drive_port.write = write
    c = Ugv01Controls(drive_port=drive_port, accel_port=sim.SimPort(boards["accel"]),
                      steer_sense="left_increases", max_duty=20, brake_absent=True)
    c.start()
    v = Ugv01Vehicle(c)
    d = BridgeDaemon(v, operators=OperatorDirectory({"pw": Operator("op", "Op")}),
                     host="127.0.0.1", port=0, log_path=tmp_path / "s.jsonl",
                     waive=("stop_on_link_loss",), bench_notes={"brake_absent": True})
    cl = _Client(None, ("t", 0), Operator("op", "Op"))
    d._driver = cl
    for _ in range(10):
        c.tick(); time.sleep(0.05)
    boards["drive"].brake = 174.0
    return boards, sent, c, v, d, cl


def test_brake_absent_on_the_jack_arm_gear_d_and_throttle_reach_the_board(tmp_path):
    """Founder, 5 Nov 2026: the brake actuator is disconnected; the wheels
    turn freely. With the bench brake-absent mode, arm, gear D and the right
    stick give duty 20 on the throttle board, and no 0x06 frame is sent."""
    boards, sent, c, v, d, cl = _rig_brake_absent(tmp_path)
    try:
        d._handle(cl, _frame(arm=False))
        d._handle(cl, _frame(arm=True))
        assert d.watchdog.state == "DRIVING"
        for _ in range(4):
            d._handle(cl, _frame(arm=True)); c.tick(); time.sleep(0.05)
        assert c.snapshot()["gear_acked"] == "D"
        for _ in range(4):
            d._handle(cl, _frame(arm=True, throttle=1.0)); c.tick(); time.sleep(0.05)
        assert v.refusals == {}, v.refusals
        assert boards["accel"].duty == 20
        assert not [f for f in sent if f.startswith(b"0x06")], sent
    finally:
        c.close()


def test_brake_absent_an_estop_latches_to_duty_zero_with_no_brake_frame(tmp_path):
    boards, sent, c, v, d, cl = _rig_brake_absent(tmp_path)
    try:
        d._handle(cl, _frame(arm=False))
        d._handle(cl, _frame(arm=True))
        for _ in range(4):
            d._handle(cl, _frame(arm=True, throttle=1.0)); c.tick(); time.sleep(0.05)
        assert boards["accel"].duty == 20
        d._handle(cl, _frame(arm=False, estop=True))
        for _ in range(4):
            c.tick(); time.sleep(0.05)
        assert d.watchdog.state == "LATCHED"
        assert boards["accel"].duty == 0
        assert not [f for f in sent if f.startswith(b"0x06")], sent
        ev = [json.loads(l) for l in open(tmp_path / "s.jsonl")]
        assert any(e["event"] == "latched" and e.get("reason") == "estop" for e in ev)
    finally:
        c.close()


def test_brake_absent_brake_sensor_trouble_does_not_block_the_arm(tmp_path):
    """In this mode the brake reading is not used, so its faults must not
    take readiness away: the self-test's brake row passes and says why."""
    boards, sent, c, v, d, cl = _rig_brake_absent(tmp_path)
    try:
        with c._lock:
            c._brake_angle = None
        rows = {r["name"]: r for r in v.self_test()}
        assert rows["brake_feedback"]["ok"] is True
        assert rows["faults"]["ok"] is True
    finally:
        c.close()
