"""ugv-01 controls: the one owner of both boards, and its safety rules.

Runs against a fake serial pair. Every rule here is a rule the bench will
test against the real boards; a change to a rule needs a bench
observation or an ADR, not a convenience.
"""
from __future__ import annotations

import queue
import re
import threading

import pytest

from pilot.hal.drivers.ugv01 import protocol as p
from pilot.hal.drivers.ugv01.controls import (
    LinkError, Refused, Ugv01Controls,
)


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.lock = threading.Lock()

    def now(self):
        with self.lock:
            return self.t

    def sleep(self, s):
        with self.lock:
            self.t += s

    def advance(self, s):
        with self.lock:
            self.t += s


class FakePort:
    """A scripted board behind a serial port.

    `answer(frame) -> list[bytes]` decides the replies. `silent` drops them.
    `opens` counts how many times the port was opened: on these boards an
    open is a reset.
    """

    def __init__(self, answer, *, silent=False):
        self.answer = answer
        self.silent = silent
        self.opens = 0
        self.is_open = False
        self.writes: list[bytes] = []
        self.rx: queue.Queue[bytes] = queue.Queue()

    def open(self):
        self.opens += 1
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, data: bytes):
        if not self.is_open:
            raise OSError("port closed")
        self.writes.append(data)
        if not self.silent:
            for line in self.answer(data):
                self.rx.put(line)

    def readline(self) -> bytes:
        try:
            return self.rx.get(timeout=0.02)
        except queue.Empty:
            return b""


def drive_board(frame: bytes) -> list[bytes]:
    text = frame.decode().strip()
    cmd = int(text.split()[0], 16)
    if cmd == p.INFO:
        return [b"0x01;OK;040103\n"]
    if cmd == p.STATUS:
        return [b"0x16;OK;D0N1\n"]
    if cmd == p.READ_STEER:
        return [b"0x04;OK;0601\n"]
    if cmd == p.READ_BRAKE:
        return [b"0x03;OK;0263\n"]
    if cmd == p.STR_LIM:
        return [b"0x10;OK;029E097E\n"]
    if cmd == p.BRK_LIM:
        return [b"0x0F;OK;01F40457\n"]
    return [("0x%02X;OK\n" % cmd).encode()]


def accel_board(frame: bytes) -> list[bytes]:
    text = frame.decode().strip()
    if text == "0x01":
        return [b"0x01;OK;AC0102\n"]
    if text.startswith("0x02;"):
        return [("0x02;OK;%s\n" % text.split(";")[1]).encode()]
    return [b"ERR;UNKNOWN_COMMAND\n"]


LOCKED = re.compile(rb"^0x(0C|0D|0E|11|12|13)\b|^0x(0F|10) ")


@pytest.fixture
def rig():
    clock = FakeClock()
    drive = FakePort(drive_board)
    accel = FakePort(accel_board)
    c = Ugv01Controls(
        drive_port=drive, accel_port=accel,
        now=clock.now, sleep=clock.sleep,
        accel_boot_s=2.5, reply_timeout_s=1.0, heartbeat_timeout_s=0.7,
        max_duty=90, poll_hz=0,
    )
    yield c, drive, accel, clock
    c.close()
    for port in (drive, accel):
        for w in port.writes:
            assert not LOCKED.match(w), "locked command reached the wire: %r" % w


def wait_until(pred, tries=200):
    import time
    for _ in range(tries):
        if pred():
            return True
        time.sleep(0.005)
    return False



def poll_once(c, clock):
    """One angle poll through the controls, for rigs built with poll_hz=0:
    a steering move needs a fresh reading (Phase A rule)."""
    import time
    c._poll_period = 0.2
    clock.advance(0.21); c.tick(); time.sleep(0.04)
    c._poll_period = None


# ------------------------------------------------------------------ start

def test_start_asks_before_it_touches_anything(rig):
    c, drive, accel, clock = rig
    c.start()
    assert drive.writes[0] == p.info()
    assert set(drive.writes) <= {p.info(), p.status(), p.read_steer_limits(),
                                 p.read_brake_limits(), p.read_steer(), p.read_brake()}
    # the accelerator board reboots on open: nothing is sent during its boot,
    # then the first frame is duty zero, then the version question
    assert accel.opens == 1
    assert accel.writes[:2] == [p.ACCEL_ZERO, p.accel_info()]
    snap = c.snapshot()
    assert snap["drive"]["firmware"] == "4.1.3"
    assert snap["accel"]["firmware"] == "1.2"
    assert snap["steer"]["angle_deg"] == 153.7
    assert snap["steer"]["limits_deg"] == (67.0, 243.0)
    assert snap["brake"]["angle_deg"] == 61.1
    assert snap["brake"]["limits_deg"] == (50.0, 111.1)


def test_start_fails_closed_when_the_drive_board_is_silent():
    clock = FakeClock()
    drive = FakePort(drive_board, silent=True)
    accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0)
    with pytest.raises(LinkError):
        c.start()
    assert accel.opens == 0, "the accelerator board was never opened"
    assert not drive.is_open


def test_start_fails_closed_when_the_accel_board_is_silent():
    clock = FakeClock()
    drive = FakePort(drive_board)
    accel = FakePort(accel_board, silent=True)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0)
    with pytest.raises(LinkError):
        c.start()
    assert accel.writes[0] == p.ACCEL_ZERO
    assert not accel.is_open and not drive.is_open


# --------------------------------------------------------------- throttle

def test_throttle_is_refused_until_the_brake_is_known_released(rig):
    c, drive, accel, clock = rig
    c.start()
    with pytest.raises(Refused, match="brake"):
        c.set_throttle(30)
    assert p.accel_duty(30) not in accel.writes
    c.brake("release")
    assert wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.set_throttle(30)
    assert accel.writes[-1] == p.accel_duty(30)


def test_throttle_is_capped_and_zero_is_always_allowed(rig):
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.set_throttle(100)
    assert accel.writes[-1] == p.accel_duty(90)
    c.brake("apply")
    c.set_throttle(0)        # never refused
    assert accel.writes[-1] == p.ACCEL_ZERO


def test_brake_apply_zeroes_the_throttle_before_the_brake_moves(rig):
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.set_throttle(40)
    order = []
    accel.write = lambda d, _w=accel.write: (order.append(("accel", d)), _w(d))
    drive.write = lambda d, _w=drive.write: (order.append(("drive", d)), _w(d))
    c.brake("apply")
    assert order[0] == ("accel", p.ACCEL_ZERO)
    assert ("drive", p.brake("apply")) in order
    assert c.snapshot()["brake"]["applied"] is True
    with pytest.raises(Refused):
        c.set_throttle(40)


def test_throttle_is_refused_when_the_accel_board_stops_answering(rig):
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.set_throttle(40)
    accel.silent = True
    c.set_throttle(45)            # written, never answered
    clock.advance(1.1)
    c.tick()
    assert accel.writes[-1] == p.ACCEL_ZERO
    assert c.snapshot()["accel"]["alive"] is False
    with pytest.raises(Refused, match="accel"):
        c.set_throttle(40)


# --------------------------------------------------------------- watchdog

def test_heartbeat_silence_with_motion_commanded_safe_stops_in_order(rig):
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    poll_once(c, clock)
    c.heartbeat()
    c.set_throttle(40)
    c.steer("left")
    accel.writes.clear(); drive.writes.clear()
    clock.advance(0.71)
    c.tick()
    assert accel.writes[0] == p.ACCEL_ZERO
    assert drive.writes[:2] == [p.brake("apply"), p.steer("stop")]
    snap = c.snapshot()
    assert snap["safe_stopped"] is True
    assert snap["brake"]["applied"] is True


def test_heartbeat_keeps_motion_alive(rig):
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.heartbeat()
    c.set_throttle(40)
    import time
    for _ in range(5):
        clock.advance(0.5)
        c.heartbeat()
        c.tick()
        time.sleep(0.03)     # the reader thread answers the liveness probe
    assert p.brake("apply") not in drive.writes
    assert c.snapshot()["safe_stopped"] is False


def test_safe_stop_is_idempotent_and_survives_a_dead_drive_link(rig):
    c, drive, accel, clock = rig
    c.start()
    drive.close()
    drive.write = lambda d: (_ for _ in ()).throw(OSError("gone"))
    c.safe_stop()
    c.safe_stop()
    assert accel.writes[-1] == p.ACCEL_ZERO
    assert c.snapshot()["safe_stopped"] is True


# ------------------------------------------------------------------ steer

def test_steer_moves_are_momentary_and_stop_is_a_real_frame(rig):
    c, drive, accel, clock = rig
    c.start()
    poll_once(c, clock)
    c.steer("left")
    c.steer("stop")
    assert drive.writes[-2:] == [p.steer("left"), p.steer("stop")]


def test_steer_to_angle_is_refused_until_the_sense_is_known(rig):
    c, drive, accel, clock = rig
    c.start()
    with pytest.raises(Refused, match="sense"):
        c.steer_to(150.0)


def test_steer_to_angle_closes_the_loop_and_stops_inside_the_deadband():
    import time
    clock = FakeClock()
    angle = {"v": 0x0601, "moving": 0}
    def board(frame):
        # the actuator keeps moving until told to stop; each angle read
        # happens 2 deg further along. Right increases the reading.
        text = frame.decode().strip()
        if text == "0x05 02":
            angle["moving"] = 20
        if text == "0x05 01":
            angle["moving"] = -20
        if text == "0x05 00":
            angle["moving"] = 0
        if text == "0x04":
            angle["v"] += angle["moving"]
            return [("0x04;OK;%04X\n" % angle["v"]).encode()]
        return drive_board(frame)
    drive = FakePort(board)
    accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=5, steer_sense="right_increases",
                      steer_deadband_deg=1.0, feedback_max_age_s=0.5)
    c.start()
    clock.advance(0.2); c.tick(); time.sleep(0.03)     # a fresh reading first
    c.steer_to(160.0)
    for _ in range(12):
        clock.advance(0.2)
        c.heartbeat()
        c.tick()                      # polls the angle through the controls
        time.sleep(0.03)              # let the reader thread take the reply
        c.tick()                      # acts on the fresh reading
    steer_frames = [w for w in drive.writes if w.startswith(b"0x05")]
    assert steer_frames[0] == p.steer("right")
    assert steer_frames[-1] == p.steer("stop")
    assert abs(c.snapshot()["steer"]["angle_deg"] - 160.0) <= 1.0
    c.close()


def test_steer_to_never_targets_outside_the_limits():
    clock = FakeClock()
    drive = FakePort(drive_board)
    accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0, steer_sense="right_increases")
    c.start()
    c.steer_to(300.0)
    assert c.snapshot()["steer"]["target_deg"] == 243.0
    c.steer_to(10.0)
    assert c.snapshot()["steer"]["target_deg"] == 67.0
    c.close()


# ------------------------------------------------------------------ close

def test_close_zeroes_the_throttle_and_stops_before_the_ports_close(rig):
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.set_throttle(40)
    c.close()
    assert accel.writes[-1] == p.ACCEL_ZERO
    assert not accel.is_open and not drive.is_open
    assert p.brake("apply") in drive.writes


def test_the_other_controls_pass_straight_through(rig):
    c, drive, accel, clock = rig
    c.start()
    c.gear("N"); c.speed_mode(1); c.light("low"); c.indicator("left"); c.horn()
    assert drive.writes[-5:] == [p.gear("N"), p.speed_mode(1), p.light("low"),
                                 p.indicator("left"), p.horn()]
    snap = c.snapshot()
    assert snap["commanded"]["gear"] == "N"
    assert snap["commanded"]["light"] == "low"
    assert snap["commanded"]["indicator"] == "left"


# ------------------------------------------- Codex checkpoint 2 regressions

class DelayedBoard:
    """A drive board whose brake acknowledgements can be held back and
    released later, in order."""

    def __init__(self):
        self.held: list[bytes] = []
        self.hold = False

    def __call__(self, frame: bytes) -> list[bytes]:
        text = frame.decode().strip()
        if text.startswith("0x06") and self.hold:
            self.held.append(("0x06;OK\n").encode())
            return []
        return drive_board(frame)


def test_a_late_apply_ack_does_not_count_as_the_release_ack():
    """Codex finding 1: APPLY, RELEASE, then the APPLY's ack arrives. The
    brake must still count as applied until the RELEASE itself is acked."""
    import time
    clock = FakeClock()
    board = DelayedBoard()
    drive = FakePort(board)
    accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0)
    c.start()
    board.hold = True
    c.brake("apply")
    c.brake("release")
    # the APPLY ack arrives first
    drive.rx.put(board.held.pop(0)); time.sleep(0.05)
    assert c.snapshot()["brake"]["applied"] is True
    with pytest.raises(Refused, match="brake"):
        c.set_throttle(20)
    drive.rx.put(board.held.pop(0)); time.sleep(0.05)
    assert c.snapshot()["brake"]["applied"] is False
    c.close()


def test_gear_needs_the_latest_zero_acked_not_an_old_one(rig):
    """Codex finding 1b: the startup zero was acked; a later 40 then 0 whose
    0 is not yet acked must not let the gear change through."""
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.set_throttle(40)
    wait_until(lambda: c.snapshot()["accel"]["duty_acked"] == 40)
    accel.silent = True
    c.set_throttle(0)            # written, not yet acked
    with pytest.raises(Refused, match="zero"):
        c.gear("R")
    accel.silent = False
    accel.rx.put(b"0x02;OK;00\n")
    wait_until(lambda: c.snapshot()["accel"]["duty_acked"] == 0)
    c.gear("R")
    assert drive.writes[-1] == p.gear("R")


def test_start_fails_when_the_drive_board_answers_err_or_withholds_state():
    """Codex finding 2: INFO answered with ERR, or limits never answered,
    is not a start."""
    def bad_info(frame):
        if frame == p.info():
            return [b"0x01;ERR;NOPE\n"]
        return drive_board(frame)
    def no_limits(frame):
        if frame == p.read_steer_limits():
            return []
        return drive_board(frame)
    for board in (bad_info, no_limits):
        clock = FakeClock()
        drive = FakePort(board); accel = FakePort(accel_board)
        c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                          sleep=clock.sleep, poll_hz=0)
        with pytest.raises(LinkError):
            c.start()
        assert not drive.is_open


def test_unsupported_firmware_is_refused_at_start():
    def v5(frame):
        if frame == p.info():
            return [b"0x01;OK;050000\n"]
        return drive_board(frame)
    clock = FakeClock()
    drive = FakePort(v5); accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0)
    with pytest.raises(LinkError, match="firmware"):
        c.start()


def test_a_failed_write_on_one_link_stops_through_the_other(rig):
    """Codex finding 3: a write exception must latch and stop, not just
    record a fault."""
    c, drive, accel, clock = rig
    c.start()
    poll_once(c, clock)
    c.heartbeat()
    c.steer("left")
    accel.writes.clear()
    drive.write = lambda d: (_ for _ in ()).throw(OSError("gone"))
    c.light("low")               # the failing write
    snap = c.snapshot()
    assert snap["faults"] and snap["safe_stopped"] is True
    assert accel.writes and accel.writes[0] == p.ACCEL_ZERO
    assert snap["stop"]["requested"] is True and snap["stop"]["acked"] is False


def test_invalid_input_changes_no_state(rig):
    """Codex finding 6."""
    c, drive, accel, clock = rig
    c.start()
    c.brake("release")
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.set_throttle(30)
    with pytest.raises(ValueError):
        c.set_throttle(-1)
    assert c.snapshot()["accel"]["duty_commanded"] == 30
    c2 = Ugv01Controls(drive_port=FakePort(drive_board), accel_port=FakePort(accel_board),
                       now=clock.now, sleep=clock.sleep, poll_hz=0, steer_sense="right_increases")
    c2.start()
    with pytest.raises(ValueError):
        c2.steer_to(float("nan"))
    assert c2.snapshot()["steer"]["target_deg"] is None
    c2.close()


def test_stale_steering_feedback_stops_the_loop():
    """Codex finding 4: no fresh angle, no steering move."""
    import time
    clock = FakeClock()
    drive = FakePort(drive_board); accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=5, steer_sense="right_increases",
                      feedback_max_age_s=0.1)
    c.start()
    clock.advance(0.2); c.tick(); time.sleep(0.03)     # one poll, fresh angle
    c.heartbeat()
    c.steer_to(200.0)
    c.tick()
    steer_frames = [w for w in drive.writes if w.startswith(b"0x05")]
    assert steer_frames[-1] == p.steer("right")
    clock.advance(0.15)           # past the freshness limit, before the next poll
    c.heartbeat()
    c.tick()
    steer_frames = [w for w in drive.writes if w.startswith(b"0x05")]
    assert steer_frames[-1] == p.steer("stop")
    assert c.snapshot()["steer"]["target_deg"] is None
    c.close()


def test_fragmented_lines_are_assembled_before_parsing():
    import time
    clock = FakeClock()
    drive = FakePort(drive_board); accel = FakePort(accel_board)
    def fragments(frame):
        if frame == p.read_steer():
            return [b"0x04;OK;0", b"700\n"]      # one reply, two reads
        return drive_board(frame)
    drive = FakePort(fragments)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=5)
    c.start()
    clock.advance(0.2); c.tick(); time.sleep(0.08)
    assert c.snapshot()["steer"]["angle_deg"] == 179.2


def test_stop_report_is_requested_and_acked_separately(rig):
    c, drive, accel, clock = rig
    c.start()
    assert c.snapshot()["stop"] == {"requested": False, "acked": False}
    c.safe_stop()
    wait_until(lambda: c.snapshot()["stop"]["acked"])
    assert c.snapshot()["stop"] == {"requested": True, "acked": True}
    c.clear_faults()
    assert c.snapshot()["stop"]["acked"] is False     # cleared, not manufactured


# ------------------------------------------------ Phase A, 13 Oct: feedback integrity

def test_a_no_signal_or_err_angle_reply_latches_a_fault():
    """Seen on the vehicle: the horn pulse made the board answer
    0x04;ERR;NO_SIGNAL and then angles outside its own limits. Feedback
    that fails must stop everything and latch."""
    import time
    clock = FakeClock()
    state = {"mode": "ok"}
    def board(frame):
        if frame == p.read_steer() and state["mode"] == "err":
            return [b"0x04;ERR;NO_SIGNAL\n"]
        return drive_board(frame)
    drive = FakePort(board); accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=5)
    c.start()
    state["mode"] = "err"
    clock.advance(0.25); c.tick(); time.sleep(0.05)
    snap = c.snapshot()
    assert any("NO_SIGNAL" in f for f in snap["faults"])
    assert snap["safe_stopped"] is True
    with pytest.raises(Refused):
        c.steer("left")
    c.close()


def test_an_implausible_angle_jump_or_out_of_range_reading_latches_a_fault():
    import time
    clock = FakeClock()
    state = {"angle": 0x0601}
    def board(frame):
        if frame == p.read_steer():
            return [("0x04;OK;%04X\n" % state["angle"]).encode()]
        return drive_board(frame)
    drive = FakePort(board); accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=5, max_angle_step_deg=30.0)
    c.start()
    state["angle"] = 0x0DC6        # 352.6: a 199 deg jump, and above the 243 limit
    clock.advance(0.25); c.tick(); time.sleep(0.05)
    snap = c.snapshot()
    assert snap["faults"] and snap["safe_stopped"] is True
    assert snap["steer"]["angle_deg"] == 153.7, "the bad reading does not replace the last good one"
    c.close()


def test_stop_frames_go_out_even_when_the_accel_write_fails(rig):
    c, drive, accel, clock = rig
    c.start()
    accel.write = lambda d: (_ for _ in ()).throw(OSError("gone"))
    c.safe_stop()
    assert drive.writes[-1] == p.steer("stop")


def test_read_status_refreshes_the_raw_status(rig):
    c, drive, accel, clock = rig
    c.start()
    drive.answer = lambda frame: [b"0x16;OK;A=00,ST=00,BR=00,SP=02,GR=01,LI=00,IN=00,HO=00,WI=00,CT=00\n"] \
        if frame == p.status() else drive_board(frame)
    c.read_status()
    assert wait_until(lambda: "GR=01" in (c.snapshot()["drive"]["status_raw"] or ""))


def test_a_release_answered_at_limit_counts_as_released():
    """Phase C2 on the vehicle: 0x06 02 answered 0x06;ERR;AT_LIMIT with the
    brake already at its released end. That is released, not applied."""
    import time
    clock = FakeClock()
    def board(frame):
        if frame == p.brake("release"):
            return [b"0x06;ERR;AT_LIMIT\n"]
        return drive_board(frame)
    drive = FakePort(board); accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0)
    c.start()
    c.brake("release")
    assert wait_until(lambda: not c.snapshot()["brake"]["applied"])
    assert c.snapshot()["faults"] == []
    c.set_throttle(20)
    assert accel.writes[-1] == p.accel_duty(20)
    c.close()


def test_other_brake_errors_do_not_release(rig):
    c, drive, accel, clock = rig
    c.start()
    drive.answer = lambda frame: [b"0x06;ERR;STALL\n"] if frame == p.brake("release") else drive_board(frame)
    c.brake("release")
    clock.advance(0.3)
    assert c.snapshot()["brake"]["applied"] is True
    with pytest.raises(Refused, match="brake"):
        c.set_throttle(20)


# ---------------------------------------------- Codex, before the first brake pulse

def test_a_brake_move_counts_as_motion_for_the_heartbeat(rig):
    c, drive, accel, clock = rig
    c.start()
    c.heartbeat()
    c.brake("apply")           # the actuator is now moving
    drive.writes.clear()
    clock.advance(0.71)
    c.tick()
    assert p.brake("stop") in drive.writes, "silence while the brake moves must stop the actuator"


def test_safe_stop_without_brake_on_stop_still_halts_the_brake_actuator():
    clock = FakeClock()
    drive = FakePort(drive_board); accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0, brake_on_stop=False)
    c.start()
    c.brake("release")
    drive.writes.clear(); accel.writes.clear()
    c.safe_stop()
    assert accel.writes[0] == p.ACCEL_ZERO
    assert drive.writes == [p.brake("stop"), p.steer("stop")]
    c.close()


def test_brake_stop_clears_the_moving_state(rig):
    c, drive, accel, clock = rig
    c.start()
    c.heartbeat()
    c.brake("apply"); c.brake("stop")
    drive.writes.clear()
    clock.advance(0.71)
    c.tick()
    assert drive.writes == []
