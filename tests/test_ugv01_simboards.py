"""The board simulators behind the 14 Oct bench runner, with the watchdog
authority of firmware 4.1.6 and AC 1.4 (15 Oct 2026).

These are the stand-ins the runner is exercised against on a laptop
before anything touches the vehicle, so what they do on a poll, a motion
command and a keepalive has to match the firmware's intent exactly.
Time is passed in, so nothing here sleeps.
"""
from __future__ import annotations

import importlib.util
import pathlib
import queue

import pytest

SIM = pathlib.Path(__file__).resolve().parents[1] / "bodies/ugv-01/bench-logs/2026-10-14/simboards.py"


@pytest.fixture(scope="module")
def sim():
    spec = importlib.util.spec_from_file_location("simboards", SIM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Rx:
    def __init__(self):
        self.rx = queue.Queue()

    def lines(self):
        out = []
        while True:
            try:
                out.append(self.rx.get_nowait().decode().strip())
            except queue.Empty:
                return out


T0 = 10.0       # every board is reset at this synthetic time; boots are over


def _drive(sim, cls):
    b = cls()
    port = _Rx()
    b.reset(port, now=T0)
    return b, port


def _nano(sim, cls):
    n = cls()
    n.reset(None, now=T0 - 10.0)
    return n


# ------------------------------------------------------------- drive 4.1.6

def test_drive416_identifies_itself_and_answers_the_keepalive(sim):
    b, _ = _drive(sim, sim.Drive416)
    assert b.handle("0x01", T0) == ["0x01;OK;040106"]
    assert b.handle("0x15", T0) == ["0x15;OK;00"]
    assert b.handle("0x15 01", T0) == ["0x15;ERR;BAD_ARG"]


def test_drive416_polls_do_not_keep_a_steering_move_alive(sim):
    b, port = _drive(sim, sim.Drive416)
    t = T0
    assert b.handle("0x05 01", t) == ["0x05;OK;01"]
    for i in range(1, 9):                       # angle polls, STATUS and INFO every 100 ms
        b.handle("0x04", t + i * 0.1); b.handle("0x03", t + i * 0.1)
        b.handle("0x16", t + i * 0.1); b.handle("0x01", t + i * 0.1)
    b.tick(t + 0.79)
    assert b.steer_dir == 1 and not b.latched, "inside 800 ms: not yet"
    b.tick(t + 0.81)
    assert b.steer_dir == 0 and b.latched and b.wd == 1
    assert port.lines() == ["0x00;WD;TIMEOUT"]
    assert b.handle("0x05 01", t + 0.9) == ["0x05;ERR;WD_TRIPPED"]
    assert b.handle("0x05 00", t + 1.0) == ["0x05;OK;00"]
    assert not b.latched


def test_drive416_keepalive_and_motion_commands_keep_a_move_alive(sim):
    b, port = _drive(sim, sim.Drive416)
    t = T0
    b.handle("0x05 01", t)
    for i in range(1, 5):                         # 1.0 s left: 67 deg, inside the 243 limit
        b.handle("0x15", t + i * 0.25)
        b.tick(t + i * 0.25 + 0.1)
    assert b.steer_dir == 1 and not b.latched and port.lines() == []
    b.handle("0x05 02", t + 1.1)                  # a motion command is a refresh too
    b.tick(t + 1.85)
    assert b.steer_dir == 2 and not b.latched
    b.tick(t + 1.91)
    assert b.steer_dir == 0 and b.latched


def test_drive416_brake_moves_need_the_keepalive_as_well(sim):
    b, port = _drive(sim, sim.Drive416)
    t = T0
    b.brake = 80.0                              # 95 deg/s: the applied end is further than 800 ms away
    assert b.handle("0x06 01", t) == ["0x06;OK;01"]
    b.handle("0x16", t + 0.5); b.handle("0x03", t + 0.7)
    b.tick(t + 0.81)
    assert b.brake_dir == 0 and b.latched
    assert port.lines() == ["0x00;WD;TIMEOUT"]


def test_drive416_status_reports_the_trip_count_and_wifi_off(sim):
    b, _ = _drive(sim, sim.Drive416)
    (line,) = b.handle("0x16", T0)
    assert "WI=00" in line and line.endswith("WD=00")


def test_drive415_is_still_the_old_board_for_the_refusal_tests(sim):
    b, _ = _drive(sim, sim.Drive415)
    assert b.handle("0x01", T0) == ["0x01;OK;040105"]
    t = T0
    b.handle("0x05 01", t)
    for i in range(1, 9):
        b.handle("0x04", t + i * 0.1)             # 4.1.5: any accepted command refreshes
    b.tick(t + 0.81)
    assert b.steer_dir == 1 and not b.latched


# -------------------------------------------------------------- nano AC 1.4

def test_nano14_identifies_itself_and_answers_the_keepalive(sim):
    n = _nano(sim, sim.Nano14)
    assert n.handle("0x01", T0) == ["0x01;OK;AC0104"]
    assert n.handle("0x04", T0) == ["0x04;OK;00;00"]
    assert n.handle("0x03", T0) == ["0x03;OK;00;00"]


def test_nano14_polls_do_not_keep_the_throttle_on(sim):
    n = _nano(sim, sim.Nano14)
    t = T0
    assert n.handle("0x02;14", t) == ["0x02;OK;14"]
    for i in range(1, 9):
        n.handle("0x01", t + i * 0.1); n.handle("0x03", t + i * 0.1)
    n.tick(t + 0.79)
    assert n.duty == 20
    n.tick(t + 0.81)
    assert n.duty == 0 and n.latched and n.timeouts == 1
    assert n.handle("0x02;14", t + 1.0) == ["0x02;ERR;TIMEOUT"]
    assert n.handle("0x04", t + 1.1) == ["0x04;OK;00;01"]
    assert n.latched, "the keepalive does not clear the latch"
    assert n.handle("0x02;00", t + 1.2) == ["0x02;OK;00"]
    assert not n.latched


def test_nano14_keepalive_and_duty_frames_keep_the_throttle_on(sim):
    n = _nano(sim, sim.Nano14)
    t = T0
    n.handle("0x02;14", t)
    for i in range(1, 7):
        assert n.handle("0x04", t + i * 0.25) == ["0x04;OK;14;00"]
        n.tick(t + i * 0.25 + 0.1)
    assert n.duty == 20 and not n.latched
    n.handle("0x02;19", t + 2.0)
    n.tick(t + 2.79)
    assert n.duty == 25
    n.tick(t + 2.81)
    assert n.duty == 0 and n.latched


def test_nano13_is_still_the_old_board(sim):
    n = _nano(sim, sim.Nano13)
    assert n.handle("0x01", T0) == ["0x01;OK;AC0103"]
    assert n.handle("0x04", T0) == ["ERR;UNKNOWN_COMMAND"]
    t = T0
    n.handle("0x02;14", t)
    for i in range(1, 9):
        n.handle("0x03", t + i * 0.1)
    n.tick(t + 0.81)
    assert n.duty == 20, "AC 1.3: the read-back is a keepalive"


def test_the_board_set_defaults_to_the_new_firmware(sim):
    boards = sim.make_boards(fw="new", broken=None)
    assert isinstance(boards["drive"], sim.Drive416) and isinstance(boards["accel"], sim.Nano14)
    boards = sim.make_boards(fw="old", broken="drive")
    assert isinstance(boards["drive"], sim.Drive415) and boards["drive"].broken
    assert isinstance(boards["accel"], sim.Nano13)
