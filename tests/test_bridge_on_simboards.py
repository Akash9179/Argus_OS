"""The bridge over the real controls over the simulated boards (4.1.6,
AC 1.4): after a link-loss stop, a fresh arm must let the steering move
again. 5 Nov 2026, found on the jack: the controls' stop latch was never
lifted, so the cockpit read DRIVING while every move was refused."""
import importlib.util
import pathlib
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
