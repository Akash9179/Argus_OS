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


STATUS_OK = "A=00,ST=00,BR=00,SP=02,GR=01,LI=00,IN=00,HO=00,WI=00,CT=00,WD=00"


def drive_board(frame: bytes) -> list[bytes]:
    """The drive module as the host must find it before it will arm motion:
    firmware 4.1.6 (watchdog authority), Wi-Fi off, the 0x15 keepalive
    answered with the trip count."""
    text = frame.decode().strip()
    cmd = int(text.split()[0], 16)
    if cmd == p.INFO:
        return [b"0x01;OK;040106\n"]
    if cmd == p.STATUS:
        return [("0x16;OK;%s\n" % STATUS_OK).encode()]
    if cmd == p.KEEPALIVE:
        return [b"0x15;OK;00\n"]
    if cmd == p.READ_STEER:
        return [b"0x04;OK;0601\n"]
    if cmd == p.READ_BRAKE:
        return [b"0x03;OK;0263\n"]
    if cmd == p.STR_LIM:
        return [b"0x10;OK;029E097E\n"]
    if cmd == p.BRK_LIM:
        return [b"0x0F;OK;01F40457\n"]
    return [("0x%02X;OK\n" % cmd).encode()]


def drive_board_415(frame: bytes) -> list[bytes]:
    """4.1.5: the watchdog that any accepted command refreshes; no 0x15."""
    text = frame.decode().strip()
    cmd = int(text.split()[0], 16)
    if cmd == p.INFO:
        return [b"0x01;OK;040105\n"]
    if cmd == p.KEEPALIVE:
        return [b"0x15;ERR;UNKNOWN_COMMAND\n"]
    return drive_board(frame)


def drive_board_413(frame: bytes) -> list[bytes]:
    """4.1.3, as the vehicle answered on 4 Oct: no watchdog, STATUS in its
    undocumented shape."""
    text = frame.decode().strip()
    cmd = int(text.split()[0], 16)
    if cmd == p.INFO:
        return [b"0x01;OK;040103\n"]
    if cmd == p.STATUS:
        return [b"0x16;OK;D0N1\n"]
    if cmd == p.KEEPALIVE:
        return [b"0x15;ERR;UNKNOWN_COMMAND\n"]
    return drive_board(frame)


_accel_state = {"duty": 0, "timeouts": 0}


def accel_board(frame: bytes) -> list[bytes]:
    """The throttle board as the host must find it: AC 1.4, with the 0x04
    keepalive and the 0x03 read-back both reporting the duty it holds.
    Every start sends duty zero first, which resets the shared state."""
    text = frame.decode().strip()
    if text == "0x01":
        return [b"0x01;OK;AC0104\n"]
    if text in ("0x03", "0x04"):
        return [("%s;OK;%02X;%02X\n" % (text, _accel_state["duty"], _accel_state["timeouts"])).encode()]
    if text.startswith("0x02;"):
        _accel_state["duty"] = int(text.split(";")[1], 16)
        if _accel_state["duty"] == 0:
            _accel_state["timeouts"] = 0
        return [("0x02;OK;%s\n" % text.split(";")[1]).encode()]
    return [b"ERR;UNKNOWN_COMMAND\n"]


def accel_board_12(frame: bytes) -> list[bytes]:
    """AC 1.2: no watchdog, no read-back, no keepalive."""
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
    assert snap["drive"]["firmware"] == "4.1.6"
    assert snap["accel"]["firmware"] == "1.4"
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
    poll_once(c, clock)
    c.heartbeat()
    c.brake("release")           # a brake move is motion: the heartbeat must be live
    wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.brake("stop")
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

def test_a_brake_move_counts_as_motion_for_the_heartbeat():
    clock = FakeClock()
    drive = FakePort(drive_board); accel = FakePort(accel_board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                      sleep=clock.sleep, poll_hz=0, brake_on_stop=False)
    c.start()
    c.heartbeat()
    c.brake("release")          # the actuator is now moving
    drive.writes.clear()
    clock.advance(0.71)
    c.tick()
    assert p.brake("stop") in drive.writes, "silence while the brake moves must stop the actuator"
    c.close()


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


# ----------------------------------------- the throttle board with a watchdog (AC 1.3)

def accel_board_13(frame):
    """AC 1.3: identity AC0103, 0x03 read-back, TIMEOUT latch after silence."""
    text = frame.decode().strip()
    if text == "0x01":
        return [b"0x01;OK;AC0103\n"]
    if text == "0x03":
        return [b"0x03;OK;00;01\n"]
    if text.startswith("0x02;"):
        return [("0x02;OK;%s\n" % text.split(";")[1]).encode()]
    return [b"ERR;UNKNOWN_COMMAND\n"]


def test_keepalive_runs_faster_than_the_boards_timeout_while_throttle_is_on(rig):
    """The throttle board drops to rest after 800 ms without a duty frame
    or a keepalive. With throttle above zero the host must send the
    keepalive at least every 250 ms."""
    c, drive, accel, clock = rig
    c.start()
    c.brake("release"); wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.heartbeat(); c.set_throttle(20)
    wait_until(lambda: c.snapshot()["accel"]["duty_acked"] == 20)
    accel.writes.clear()
    import time
    for _ in range(8):
        clock.advance(0.1); c.heartbeat(); c.tick(); time.sleep(0.02)
    probes = [w for w in accel.writes if w == p.accel_keepalive()]
    assert len(probes) >= 3, accel.writes


def test_a_timeout_error_from_the_board_latches_a_fault():
    import time
    clock = FakeClock()
    def board(frame):
        text = frame.decode().strip()
        if text.startswith("0x02;") and text != "0x02;00":
            return [b"0x02;ERR;TIMEOUT\n"]
        return accel_board(frame)
    drive = FakePort(drive_board); accel = FakePort(board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now, sleep=clock.sleep, poll_hz=0)
    c.start()
    c.brake("release"); wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.heartbeat(); c.set_throttle(20)
    assert wait_until(lambda: any("TIMEOUT" in f for f in c.snapshot()["faults"]))
    assert c.snapshot()["safe_stopped"] is True
    c.close()


def test_the_read_back_reply_updates_duty_and_timeouts():
    import time
    clock = FakeClock()
    drive = FakePort(drive_board); accel = FakePort(accel_board_13)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now, sleep=clock.sleep, poll_hz=0)
    c.start()
    assert c.snapshot()["accel"]["firmware"] == "1.3"
    c.read_accel()
    assert wait_until(lambda: c.snapshot()["accel"]["timeouts"] == 1)
    assert c.snapshot()["accel"]["duty_read"] == 0
    c.close()


def test_the_drive_modules_timeout_notice_latches_a_fault(rig):
    """4.1.5 prints 0x00;WD;TIMEOUT once when it switched its actuators
    off after host silence. Unsolicited, but it is a fault report."""
    c, drive, accel, clock = rig
    c.start()
    drive.rx.put(b"0x00;WD;TIMEOUT\n")
    assert wait_until(lambda: any("WD" in f or "silence" in f for f in c.snapshot()["faults"]))
    assert c.snapshot()["safe_stopped"] is True


def test_read_back_is_only_sent_to_a_board_that_supports_it():
    """AC 1.2 answers 0x03 with ERR;UNKNOWN_COMMAND, which has no command
    byte and would leave the frame pending until a false 'not answering'
    fault. So the read-back is gated on the firmware version."""
    clock = FakeClock()
    drive = FakePort(drive_board); accel = FakePort(accel_board_12)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now, sleep=clock.sleep, poll_hz=0)
    c.start()
    before = list(accel.writes)
    c.read_accel()
    assert accel.writes == before
    assert c.snapshot()["accel"]["read_back"] is False
    c.close()


def test_on_ac14_the_keepalive_carries_the_read_back_and_a_new_timeout_faults():
    import time
    clock = FakeClock()
    state = {"timeouts": 0}
    def board(frame):
        text = frame.decode().strip()
        if text in ("0x03", "0x04"):
            return [("%s;OK;%02X;%02X\n" % (text, state.get("duty", 0), state["timeouts"])).encode()]
        if text.startswith("0x02;"):
            state["duty"] = int(text.split(";")[1], 16)
        return accel_board(frame)
    drive = FakePort(drive_board); accel = FakePort(board)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now, sleep=clock.sleep, poll_hz=0)
    c.start()
    c.brake("release"); wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.heartbeat(); c.set_throttle(20)
    wait_until(lambda: c.snapshot()["accel"]["duty_acked"] == 20)
    accel.writes.clear()
    for _ in range(3):
        clock.advance(0.3); c.heartbeat(); c.tick(); time.sleep(0.03)
    assert p.accel_keepalive() in accel.writes
    assert p.accel_read() not in accel.writes and p.accel_info() not in accel.writes
    assert c.snapshot()["accel"]["duty_read"] == 20
    # the board reports a timeout it took on its own: that is a fault here
    state["timeouts"] = 1; state["duty"] = 0
    clock.advance(0.3); c.heartbeat(); c.tick(); time.sleep(0.05)
    assert any("timeout" in f.lower() for f in c.snapshot()["faults"])
    c.close()


def test_a_board_watchdog_report_stops_without_driving_the_brake(rig):
    """The module already switched its actuators off; our stop must not
    answer with a brake apply that re-energises the actuator it just
    stopped, whatever brake_on_stop says."""
    c, drive, accel, clock = rig
    c.start()
    drive.writes.clear()
    drive.rx.put(b"0x00;WD;TIMEOUT\n")
    assert wait_until(lambda: c.snapshot()["safe_stopped"])
    assert p.brake("apply") not in drive.writes
    assert p.steer("stop") in drive.writes


def test_no_signal_notice_faults_and_the_brake_stays_out_until_cleared(rig):
    """4.1.5 prints 0x00;WD;NO_SIGNAL when it dropped an actuator for a bad
    sensor. That is a fault, and after any board-reported trip no stop,
    including close(), may re-energise the brake until a human clears."""
    c, drive, accel, clock = rig
    c.start()
    drive.rx.put(b"0x00;WD;NO_SIGNAL\n")
    assert wait_until(lambda: any("NO_SIGNAL" in f for f in c.snapshot()["faults"]))
    drive.writes.clear()
    c.safe_stop()                 # a later stop, default brake_on_stop=True in this rig
    c.close()
    assert p.brake("apply") not in drive.writes
    assert p.steer("stop") in drive.writes


# ------------------------------ watchdog authority: 4.1.6 and AC 1.4 (15 Oct)
# Only motion commands and the explicit keepalive refresh the boards'
# watchdogs; polls do not. The host arms motion only on those versions with
# Wi-Fi off, and sends the keepalive only from a live command path.

def _rig(drive_answer, accel_answer, **kw):
    clock = FakeClock()
    drive = FakePort(drive_answer); accel = FakePort(accel_answer)
    kw.setdefault("poll_hz", 0)
    c = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now, sleep=clock.sleep, **kw)
    return c, drive, accel, clock


def test_new_boards_with_wifi_off_are_armed(rig):
    c, drive, accel, clock = rig
    c.start()
    assert c.snapshot()["armed"] == {"ok": True, "reason": None}


@pytest.mark.parametrize("drive_answer, accel_answer, word", [
    (drive_board_415, accel_board, "4.1.5"),
    (drive_board, accel_board_13, "1.3"),
    (drive_board_413, accel_board_12, "4.1.3"),
])
def test_older_boards_start_but_are_not_armed_and_every_move_is_refused(drive_answer, accel_answer, word):
    c, drive, accel, clock = _rig(drive_answer, accel_answer, steer_sense="right_increases")
    c.start()                        # identity and the reads work: the bench can still look
    armed = c.snapshot()["armed"]
    assert armed["ok"] is False and word in armed["reason"], armed
    poll_once(c, clock); c.heartbeat()
    moves = (lambda: c.steer("left"), lambda: c.brake("release"), lambda: c.brake("apply"),
             lambda: c.set_throttle(10), lambda: c.steer_to(150.0))
    for move in moves:
        with pytest.raises(Refused, match="not armed"):
            move()
    energising = [w for w in drive.writes if w[:4] in (b"0x05", b"0x06") and not w.endswith(b" 00\n")]
    assert energising == []
    assert [w for w in accel.writes if w.startswith(b"0x02;") and w != p.ACCEL_ZERO] == []
    # stops, reads and the other controls still pass
    c.steer("stop"); c.brake("stop"); c.set_throttle(0); c.read_status(); c.light("low")
    for _ in range(4):
        clock.advance(0.3); c.heartbeat(); c.tick()
    c.safe_stop()
    assert p.steer("stop") in drive.writes
    assert p.keepalive() not in drive.writes, "no keepalive to a board that does not know it"
    assert p.accel_keepalive() not in accel.writes
    c.close()


def test_wifi_on_in_status_blocks_arming_at_start():
    def wifi_on(frame):
        if frame == p.status():
            return [b"0x16;OK;A=00,ST=00,BR=00,SP=02,GR=01,LI=00,IN=00,HO=00,WI=01,CT=00,WD=00\n"]
        return drive_board(frame)
    c, drive, accel, clock = _rig(wifi_on, accel_board)
    c.start()
    armed = c.snapshot()["armed"]
    assert armed["ok"] is False and "WI=01" in armed["reason"]
    with pytest.raises(Refused, match="not armed"):
        c.brake("release")
    assert c.snapshot()["faults"] == [], "at start it is a refusal, not a fault"
    c.close()


def test_a_status_without_the_wifi_field_does_not_arm():
    def no_wi(frame):
        if frame == p.status():
            return [b"0x16;OK;D0N1\n"]
        return drive_board(frame)
    c, drive, accel, clock = _rig(no_wi, accel_board)
    c.start()
    armed = c.snapshot()["armed"]
    assert armed["ok"] is False and "WI" in armed["reason"]
    c.close()


def test_wifi_coming_on_later_is_a_fault():
    state = {"wi": 0}
    def board(frame):
        if frame == p.status():
            return [("0x16;OK;A=00,ST=00,BR=00,SP=02,GR=01,LI=00,IN=00,HO=00,WI=%02X,CT=00,WD=00\n"
                     % state["wi"]).encode()]
        return drive_board(frame)
    c, drive, accel, clock = _rig(board, accel_board)
    c.start()
    assert c.snapshot()["armed"]["ok"] is True
    state["wi"] = 1
    c.read_status()
    assert wait_until(lambda: any("Wi-Fi" in f for f in c.snapshot()["faults"]))
    snap = c.snapshot()
    assert snap["safe_stopped"] is True and snap["armed"]["ok"] is False
    c.close()


def test_the_drive_keepalive_runs_while_an_actuator_moves_and_not_at_rest():
    import time
    c, drive, accel, clock = _rig(drive_board, accel_board, brake_on_stop=False)
    c.start(); poll_once(c, clock); c.heartbeat()
    c.steer("left")
    drive.writes.clear()
    for _ in range(8):                           # 0.8 s of a live host
        clock.advance(0.1); c.heartbeat(); c.tick(); time.sleep(0.02)
    ka = [w for w in drive.writes if w == p.keepalive()]
    assert len(ka) == 3, drive.writes            # at 0.1, 0.4 and 0.7 s: at least every 250 ms
    assert set(drive.writes) == {p.keepalive()}, "a live host sends nothing else at poll_hz=0"
    c.steer("stop")
    drive.writes.clear()
    for _ in range(8):
        clock.advance(0.1); c.heartbeat(); c.tick(); time.sleep(0.02)
    assert p.keepalive() not in drive.writes, "at rest nothing is required"
    c.heartbeat(); c.brake("release")            # a brake move needs it too
    drive.writes.clear()
    for _ in range(4):
        clock.advance(0.1); c.heartbeat(); c.tick(); time.sleep(0.02)
    assert p.keepalive() in drive.writes
    c.close()


def test_the_drive_keepalive_does_not_outlive_the_host_heartbeat():
    """The point of 4.1.6: a host whose command path is dead must not keep a
    move alive. The controls' own heartbeat rule stops first, and from
    then on no keepalive leaves the host."""
    import time
    c, drive, accel, clock = _rig(drive_board, accel_board, brake_on_stop=False)
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    drive.writes.clear()
    clock.advance(0.71); c.tick()
    assert p.steer("stop") in drive.writes and p.keepalive() not in drive.writes
    drive.writes.clear()
    for _ in range(8):
        clock.advance(0.1); c.tick(); time.sleep(0.02)
    assert p.keepalive() not in drive.writes
    c.close()


def test_a_poller_without_a_command_path_sends_no_keepalive():
    """The runner's poll-only mode: angle polls and STATUS through the
    controls with no tick and no heartbeat. Nothing that refreshes the
    board leaves the host, so the board must trip on its own."""
    import time
    c, drive, accel, clock = _rig(drive_board, accel_board, brake_on_stop=False)
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    drive.writes.clear()
    for _ in range(10):
        c.poll_feedback(); c.read_status(); time.sleep(0.01)
    assert set(drive.writes) == {p.read_steer(), p.read_brake(), p.status()}
    assert c.snapshot()["faults"] == []
    c.close()


def test_the_stop_brake_apply_is_kept_alive_to_its_end_and_no_longer():
    """safe_stop with brake_on_stop drives the brake toward applied. On
    4.1.6 that move needs the keepalive too, from the controls themselves,
    bounded by the stroke time; then the actuator is halted where it is."""
    import time
    c, drive, accel, clock = _rig(drive_board, accel_board, brake_on_stop=True, brake_stroke_max_s=1.0)
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    clock.advance(0.71); c.tick()                   # silent host: stop, with the brake apply
    assert p.brake("apply") in drive.writes and p.steer("stop") in drive.writes
    drive.writes.clear()
    for _ in range(8):                               # 0.8 s: inside the stroke bound
        clock.advance(0.1); c.tick(); time.sleep(0.02)
    ka = [w for w in drive.writes if w == p.keepalive()]
    assert len(ka) >= 2 and p.brake("stop") not in drive.writes, drive.writes
    drive.writes.clear()
    for _ in range(5):                               # past the bound
        clock.advance(0.1); c.tick(); time.sleep(0.02)
    assert p.brake("stop") in drive.writes, drive.writes
    after = drive.writes[drive.writes.index(p.brake("stop")) + 1:]
    assert p.keepalive() not in after
    c.close()


def test_after_a_board_trip_the_stop_sends_no_keepalive(rig):
    """The module stopped itself and is latched: nothing moves, so nothing
    is kept alive, and the brake is not applied (existing rule)."""
    import time
    c, drive, accel, clock = rig
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    drive.writes.clear()
    drive.rx.put(b"0x00;WD;TIMEOUT\n")
    assert wait_until(lambda: c.snapshot()["safe_stopped"])
    for _ in range(4):
        clock.advance(0.1); c.tick(); time.sleep(0.02)
    assert p.keepalive() not in drive.writes and p.brake("apply") not in drive.writes


def test_accel_keepalive_is_the_explicit_opcode_while_the_throttle_is_on_and_a_poll_at_rest():
    import time
    c, drive, accel, clock = _rig(drive_board, accel_board)
    c.start(); c.brake("release"); wait_until(lambda: not c.snapshot()["brake"]["applied"])
    c.heartbeat(); c.set_throttle(20); wait_until(lambda: c.snapshot()["accel"]["duty_acked"] == 20)
    accel.writes.clear()
    for _ in range(8):
        clock.advance(0.1); c.heartbeat(); c.tick(); time.sleep(0.02)
    ka = [w for w in accel.writes if w == p.accel_keepalive()]
    assert len(ka) >= 3, accel.writes
    assert p.accel_read() not in accel.writes and p.accel_info() not in accel.writes
    assert c.snapshot()["accel"]["duty_read"] == 20
    c.set_throttle(0); wait_until(lambda: c.snapshot()["accel"]["duty_acked"] == 0)
    accel.writes.clear()
    for _ in range(6):
        clock.advance(0.3); c.heartbeat(); c.tick(); time.sleep(0.03)
    assert p.accel_keepalive() not in accel.writes, "at rest the liveness probe is a poll"
    assert p.accel_read() in accel.writes
    c.close()


def test_a_rising_trip_count_in_the_drive_keepalive_reply_faults_without_the_brake():
    import time
    state = {"wd": 0}
    def board(frame):
        if frame == p.keepalive():
            return [("0x15;OK;%02X\n" % state["wd"]).encode()]
        return drive_board(frame)
    c, drive, accel, clock = _rig(board, accel_board, brake_on_stop=True)
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    for _ in range(3):
        clock.advance(0.3); c.heartbeat(); c.tick(); time.sleep(0.03)
    assert c.snapshot()["faults"] == []
    assert c.snapshot()["drive"]["trips"] == 0
    state["wd"] = 1                                  # the WD line itself was lost
    drive.writes.clear()
    clock.advance(0.3); c.heartbeat(); c.tick(); time.sleep(0.05)
    snap = c.snapshot()
    assert any("trip" in f for f in snap["faults"]) and snap["safe_stopped"] is True
    assert snap["drive"]["trips"] == 1
    assert p.brake("apply") not in drive.writes
    c.close()


def test_snapshot_reports_the_trip_count_from_status(rig):
    c, drive, accel, clock = rig
    c.start()
    assert c.snapshot()["drive"]["trips"] == 0


def test_the_trip_count_rising_after_the_boards_own_notice_is_one_fault_not_two():
    """Seen on the simulator: the WD line arrived, then the next STATUS
    carried WD=01. That is the same trip; a second fault for it would
    stop the bench's silence step from passing."""
    state = {"wd": 0}
    def board(frame):
        if frame == p.status():
            return [("0x16;OK;A=00,ST=00,BR=00,SP=02,GR=03,LI=00,IN=00,HO=00,WI=00,CT=00,WD=%02X\n"
                     % state["wd"]).encode()]
        return drive_board(frame)
    c, drive, accel, clock = _rig(board, accel_board, brake_on_stop=False)
    c.start()
    state["wd"] = 1
    drive.rx.put(b"0x00;WD;TIMEOUT\n")
    assert wait_until(lambda: c.snapshot()["safe_stopped"])
    c.read_status()
    assert wait_until(lambda: c.snapshot()["drive"]["trips"] == 1)
    assert c.snapshot()["faults"] == ["drive module WD TIMEOUT: it stopped its actuators itself"]
    c.clear_faults()
    c.read_status()
    wait_until(lambda: False, tries=10)
    assert c.snapshot()["faults"] == []
    state["wd"] = 2                               # a second trip whose notice was lost
    c.read_status()
    assert wait_until(lambda: any("trip count rose to 2" in f for f in c.snapshot()["faults"]))
    c.close()


# ------------------------------------------- Codex Astra, 15 Oct: the stop's brake apply

def test_repeated_stops_do_not_extend_the_stop_brake_window():
    """Codex finding 2: every safe_stop re-sent the apply and restarted
    the deadline, so a poller faulting every poll kept the brake moving
    for as long as it faulted. The first stop's deadline stands."""
    import time
    c, drive, accel, clock = _rig(drive_board, accel_board, brake_on_stop=True, brake_stroke_max_s=1.0)
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    clock.advance(0.71); c.tick()                   # the first stop: brake apply at t0
    for _ in range(6):                               # faults keep coming for 1.2 s
        clock.advance(0.2); c._fault("steering feedback failed: NO_SIGNAL"); c.tick(); time.sleep(0.02)
    applies = [w for w in drive.writes if w == p.brake("apply")]
    assert len(applies) == 1, drive.writes
    assert p.brake("stop") in drive.writes           # halted at the first deadline
    after = drive.writes[drive.writes.index(p.brake("stop")) + 1:]
    assert p.keepalive() not in after and p.brake("apply") not in after
    c.safe_stop()                                    # a later stop halts, it does not re-apply
    assert drive.writes[-2:] == [p.brake("stop"), p.steer("stop")]
    c.close()


def test_clear_faults_halts_a_stop_brake_move_instead_of_inheriting_it():
    """Codex finding 3: clear_faults left _brake_moving set from the stop's
    apply, so later heartbeats kept that move alive with no bound."""
    import time
    c, drive, accel, clock = _rig(drive_board, accel_board, brake_on_stop=True, brake_stroke_max_s=5.0)
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    clock.advance(0.71); c.tick()
    drive.writes.clear()
    c.clear_faults()
    assert drive.writes == [p.brake("stop")]
    for _ in range(6):
        clock.advance(0.2); c.heartbeat(); c.tick(); time.sleep(0.02)
    assert p.keepalive() not in drive.writes
    assert c.snapshot()["brake"]["applied"] is True   # applied or unknown counts as applied
    c.close()


@pytest.mark.parametrize("drive_answer", [drive_board_415, drive_board_413])
def test_safe_stop_never_applies_the_brake_on_a_board_it_has_not_armed(drive_answer):
    """Codex finding 4: the stop bypassed the arming rule. On an older board
    (or Wi-Fi on) the stop halts the brake where it is; it does not start a
    move the host could not keep alive by its own rules."""
    c, drive, accel, clock = _rig(drive_answer, accel_board, brake_on_stop=True)
    c.start()
    drive.writes.clear()
    c.safe_stop()
    assert drive.writes == [p.brake("stop"), p.steer("stop")]
    drive.writes.clear()
    c.close()
    assert p.brake("apply") not in drive.writes


def test_safe_stop_halts_the_brake_when_wifi_is_on():
    def wifi_on(frame):
        if frame == p.status():
            return [b"0x16;OK;A=00,ST=00,BR=00,SP=02,GR=01,LI=00,IN=00,HO=00,WI=01,CT=00,WD=00\n"]
        return drive_board(frame)
    c, drive, accel, clock = _rig(wifi_on, accel_board, brake_on_stop=True)
    c.start()
    drive.writes.clear()
    c.safe_stop()
    assert drive.writes == [p.brake("stop"), p.steer("stop")]
    c.close()


# ------------------------------------------- Codex Astra, 15 Oct: the bench's tick thread

def test_bench_ticker_never_feeds_the_heartbeat_and_pulse_does():
    """Codex finding 1: a tick thread that fed the heartbeat itself kept a
    stalled command thread's move alive. The ticker only ticks; the
    heartbeat comes from the command thread, only during its own pulse."""
    import threading, time
    from pilot.hal.drivers.ugv01.bench import Bench

    class Counting:
        heartbeats = 0; ticks = 0
        def heartbeat(self): self.heartbeats += 1
        def tick(self): self.ticks += 1
    fake = Counting()
    b = Bench(fake, log=None)
    t = threading.Thread(target=b.ticker, daemon=True); t.start()
    time.sleep(0.2); b.stop.set(); t.join(1.0)
    assert fake.ticks >= 2 and fake.heartbeats == 0
    b = Bench(fake, log=None)
    b.pulse(0.12)
    assert fake.heartbeats >= 2
    n = fake.heartbeats
    b.pulse(1.0, until=lambda: True)         # the closed loop's exit: no feed once reached
    assert fake.heartbeats == n


def test_a_second_stop_inside_the_window_keeps_the_stop_brake_stroke_running():
    """Codex second look, finding 2: the bridge sends safe_stop on every held
    estop frame. A stop inside the first stop's window must neither re-apply
    nor halt the running stroke; a board trip inside it halts at once."""
    c, drive, accel, clock = _rig(drive_board, accel_board, brake_on_stop=True, brake_stroke_max_s=1.0)
    c.start(); poll_once(c, clock); c.heartbeat(); c.steer("left")
    clock.advance(0.71); c.tick()                   # the first stop: brake apply at t0
    assert drive.writes.count(p.brake("apply")) == 1
    n = len(drive.writes)
    for _ in range(4):
        clock.advance(0.1); c.safe_stop(); c.tick()
    since = drive.writes[n:]
    assert p.brake("stop") not in since and p.brake("apply") not in since, since
    assert c._brake_moving is True
    clock.advance(0.1); c._fault("drive module WD TIMEOUT: it stopped its actuators itself", brake=False)
    assert c._brake_moving is False
    assert drive.writes[-2:] == [p.brake("stop"), p.steer("stop")]
    c.close()
