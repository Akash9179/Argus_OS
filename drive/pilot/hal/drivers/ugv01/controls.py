"""The one owner of ugv-01's two boards, and every safety rule about them.

Two boards, two ports, one object. Nothing else in ARGUS writes to either
port. The teleop bridge adapter and the HAL locomotion driver both sit on
top of this class (ADR-0009: the hardware is driven from exactly one
place).

What this class guarantees, and what it cannot:

- It starts inhibited and unknown. Open is treated as a reset. Start
  fails closed unless both boards identify themselves with a supported
  firmware, the drive board answers STATUS, both limits and both angles,
  and the accelerator board acknowledges duty zero. No actuator frame is
  sent during start.
- Every frame is a transaction: the reply that answers it is the oldest
  unanswered frame with the same command byte, and for the accelerator
  the reply must echo the duty that was sent. A late acknowledgement of
  an earlier frame never stands in for a later one.
- Throttle is refused until the accelerator has acknowledged a duty of
  zero and the brake release frame itself has been acknowledged. A gear
  change needs the latest duty-zero frame acknowledged, not an old one.
- It never sends a locked, admin, reset, Wi-Fi or limit-write command
  (protocol.py has no encoder for them). It never auto-centres steering:
  that is a move, not a stop.
- A quiet accelerator gets a liveness probe every `accel_probe_s`; both
  links have reply deadlines; the steering loop stops on feedback older
  than `feedback_max_age_s`. Any board fault, any failed write, or a
  silent host heartbeat while motion is commanded triggers `safe_stop()`:
  accelerator duty zero first, then (if `brake_on_stop`) brake apply,
  then steering stop, each attempted whatever happened to the one before.
  Faults latch until `clear_faults()`, a human decision.

What it cannot guarantee, stated so nobody reads more into it: a host
cannot command a board through a link that has failed, and neither
board's firmware is known to have a watchdog. `snapshot()["stop"]`
reports "requested" and "acked" separately; acknowledged means the board
answered, not that the vehicle is physically stopped. Until a stop on
link loss is proven on both boards, the hardware safety gate in
ARCHITECTURE.md section 6 stays shut.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from pilot.hal.drivers.ugv01 import protocol as p
from pilot.hal.drivers.ugv01.link import Port


class LinkError(RuntimeError):
    """A board did not answer when it had to, or is not the board we know."""


class Refused(RuntimeError):
    """A command was not sent, and the reason is in the message."""


STEER_SENSES = ("right_increases", "left_increases")
SUPPORTED_DRIVE_FIRMWARE = ("4.1.",)     # ARGUS DRIVE 4.1.x
SUPPORTED_ACCEL_FIRMWARE = ("1.",)       # accelerator board 1.x


@dataclass
class _Txn:
    seq: int
    cmd: int
    arg: int | None
    sent_at: float
    reply: p.Reply | None = None


@dataclass
class _Link:
    name: str
    port: Port
    connected: bool = False      # port open and no write has failed
    answering: bool = False      # replies arriving within the deadline
    firmware: str | None = None
    last_reply_at: float | None = None
    pending: deque = field(default_factory=deque)   # _Txn, oldest first
    thread: threading.Thread | None = None
    stop: threading.Event = field(default_factory=threading.Event)


class Ugv01Controls:
    def __init__(
        self,
        *,
        drive_port: Port,
        accel_port: Port,
        now=time.monotonic,
        sleep=time.sleep,
        accel_boot_s: float = 2.5,
        drive_boot_s: float = 0.5,
        reply_timeout_s: float = 1.0,
        heartbeat_timeout_s: float = 0.7,
        accel_probe_s: float = 0.25,     # AC 1.3 rests after 800 ms of silence; talk 3x faster
        feedback_max_age_s: float = 0.5,
        max_angle_step_deg: float = 30.0,
        max_duty: int = 90,
        poll_hz: float = 5.0,
        steer_sense: str | None = None,
        steer_deadband_deg: float = 1.0,
        brake_on_stop: bool = True,
        on_line=None,
        on_tx=None,
    ) -> None:
        """`on_line(link_name, line)` sees every decoded line from either
        board; `on_tx(link_name, frame)` every frame written. Both are for
        the bench log and run on whichever thread did the work.
        `brake_on_stop=False` leaves the brake out of safe_stop(): for a
        bench that has not yet characterised the brake stroke."""
        if steer_sense is not None and steer_sense not in STEER_SENSES:
            raise ValueError("steer_sense must be one of %s" % (STEER_SENSES,))
        if not 0 <= max_duty <= 100:
            raise ValueError("max_duty must be 0 to 100")
        self._now = now
        self._sleep = sleep
        self._accel_boot_s = accel_boot_s
        self._drive_boot_s = drive_boot_s
        self._reply_timeout = reply_timeout_s
        self._hb_timeout = heartbeat_timeout_s
        self._accel_probe_s = accel_probe_s
        self._feedback_max_age = feedback_max_age_s
        self._max_angle_step = max_angle_step_deg
        self._max_duty = max_duty
        self._poll_period = (1.0 / poll_hz) if poll_hz > 0 else None
        self._steer_sense = steer_sense
        self._deadband = steer_deadband_deg
        self._brake_on_stop = brake_on_stop
        self._on_line_hook = on_line
        self._on_tx_hook = on_tx

        self._lock = threading.RLock()
        self._drive = _Link("drive", drive_port)
        self._accel = _Link("accel", accel_port)
        self._seq = 0
        self._answered: dict[int, _Txn] = {}   # answered txns, kept briefly for _await
        self._started = False
        self._closing = False

        # drive board state, from replies
        self._status_raw: str | None = None
        self._steer_angle: float | None = None
        self._steer_angle_at: float | None = None
        self._brake_angle: float | None = None
        self._steer_limits: tuple[float, float] | None = None
        self._brake_limits: tuple[float, float] | None = None
        # intent and acknowledgement
        self._brake_applied: bool = True      # unknown counts as applied
        self._brake_release_seq: int | None = None
        self._accel_alive = False             # duty zero acknowledged since open
        self._duty_commanded = 0
        self._duty_acked: int | None = None
        self._duty_last_seq: int | None = None
        self._duty_acked_seq: int | None = None
        self._duty_read: int | None = None      # AC 1.3 read-back
        self._accel_timeouts: int | None = None
        self._accel_read_back = False           # firmware 1.3 or later
        self._board_tripped = False             # a board stopped itself: no brake apply until cleared
        self._steer_moving: str = "stop"
        self._steer_target: float | None = None
        self._brake_moving: bool = False      # apply or release in progress
        self._commanded = {"gear": None, "light": None, "indicator": None, "speed_mode": None}
        # supervision
        self._last_heartbeat: float | None = None
        self._last_poll_at: float | None = None
        self._last_accel_probe_at: float | None = None
        self._safe_stopped = False
        self._in_stop = False
        self._faults: list[str] = []
        self._stop_requested = False
        self._stop_seqs: set[int] = set()
        self._stop_acked_seqs: set[int] = set()

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Open both boards and interrogate them. Sends no actuator frame.
        Raises LinkError and closes everything on any missing answer."""
        with self._lock:
            if self._started:
                return
            self._closing = False
        # not under the lock: the reader threads need it to deliver replies
        try:
            self._open_drive()
            self._open_accel()
        except Exception:
            self._close_ports()
            raise
        with self._lock:
            self._started = True
            self._last_poll_at = self._now()

    def _open_drive(self) -> None:
        d = self._drive
        d.port.open()
        d.connected = True
        d.stop.clear()
        d.thread = threading.Thread(target=self._reader, args=(d,), daemon=True,
                                    name="ugv01-drive-reader")
        d.thread.start()
        self._sleep(self._drive_boot_s)           # open may be a reset
        r = self._ask(d, p.info(), p.INFO)
        version = p.firmware_version(r.data) if r and r.ok else None
        if version is None:
            raise LinkError("drive board did not identify itself on %s" % _name(d))
        if not version.startswith(SUPPORTED_DRIVE_FIRMWARE):
            raise LinkError("drive board firmware %s is not a supported version (%s)"
                            % (version, SUPPORTED_DRIVE_FIRMWARE))
        with self._lock:
            d.firmware = version
        wanted = (
            (p.status(), p.STATUS, lambda: self._status_raw is not None, "STATUS"),
            (p.read_steer_limits(), p.STR_LIM, lambda: self._steer_limits is not None, "steering limits"),
            (p.read_brake_limits(), p.BRK_LIM, lambda: self._brake_limits is not None, "brake limits"),
            (p.read_steer(), p.READ_STEER, lambda: self._steer_angle is not None, "steering angle"),
            (p.read_brake(), p.READ_BRAKE, lambda: self._brake_angle is not None, "brake angle"),
        )
        for frame, cmd, have, what in wanted:
            self._ask(d, frame, cmd)
            with self._lock:
                ok = have()
            if not ok:
                raise LinkError("drive board did not answer %s on %s" % (what, _name(d)))

    def _open_accel(self) -> None:
        a = self._accel
        a.port.open()
        a.connected = True
        a.stop.clear()
        a.thread = threading.Thread(target=self._reader, args=(a,), daemon=True,
                                    name="ugv01-accel-reader")
        a.thread.start()
        self._sleep(self._accel_boot_s)           # the board reboots on open
        with self._lock:
            self._duty_commanded = 0
        seq = self._write(a, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD, arg=0)
        with self._lock:
            self._duty_last_seq = seq
        r = self._await(seq) if seq is not None else None
        with self._lock:
            alive = self._accel_alive
        if not alive:
            raise LinkError("accelerator board did not acknowledge duty zero on %s" % _name(a))
        r = self._ask(a, p.accel_info(), p.ACCEL_INFO_CMD)
        version = p.accel_version(r.data) if r and r.ok else None
        if version is None:
            raise LinkError("accelerator board did not identify itself on %s" % _name(a))
        if not version.startswith(SUPPORTED_ACCEL_FIRMWARE):
            raise LinkError("accelerator firmware %s is not a supported version" % version)
        with self._lock:
            a.firmware = version
            try:
                self._accel_read_back = tuple(int(x) for x in version.split(".")) >= (1, 3)
            except ValueError:
                self._accel_read_back = False

    def close(self) -> None:
        """Stop first, wait for the boards to answer, then let go. Closing
        a port may reset the board behind it; nothing relies on that."""
        with self._lock:
            started = self._started
            self._started = False
            self._closing = True
        if started:
            self.safe_stop()
            seq = self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD, arg=0)
            for s in list(self._stop_seqs) + ([seq] if seq else []):
                self._await(s)
        self._close_ports()

    def _close_ports(self) -> None:
        for link in (self._accel, self._drive):
            link.stop.set()
            link.connected = False
            try:
                link.port.close()
            except Exception:
                pass
        for link in (self._accel, self._drive):
            t = link.thread
            if t is not None and t is not threading.current_thread():
                t.join(timeout=1.0)

    # -------------------------------------------------------------- readers

    def _reader(self, link: _Link) -> None:
        buf = bytearray()
        while not link.stop.is_set():
            try:
                raw = link.port.readline()
            except Exception as e:  # noqa: BLE001
                if not link.stop.is_set():
                    self._fault("%s link lost (%s)" % (link.name, type(e).__name__),
                                link, port_dead=True)
                return
            if not raw:
                continue
            buf.extend(raw)
            # a timed-out read can hand back half a line; only whole lines count
            while b"\n" in buf:
                line_bytes, _, rest = buf.partition(b"\n")
                buf = bytearray(rest)
                line = p.decode_line(line_bytes)
                if line:
                    self._on_line(link, line)

    def _on_line(self, link: _Link, line: str) -> None:
        if self._on_line_hook is not None:
            try:
                self._on_line_hook(link.name, line)
            except Exception:  # noqa: BLE001
                pass
        reply = p.parse_reply(line)
        with self._lock:
            link.last_reply_at = self._now()
            link.answering = True
            if line.strip().upper().startswith("0X00;WD;"):
                # 4.1.5: the drive module switched its actuators off on its
                # own (TIMEOUT after host silence, NO_SIGNAL for a sensor).
                # Unsolicited, and a fault on our side.
                self._fault("drive module WD %s: it stopped its actuators itself" % line.split(";")[-1].strip(),
                            brake=False)
                return
            if reply is None:
                return
            txn = None
            for i, t in enumerate(link.pending):
                if t.cmd == reply.cmd:
                    txn = t
                    del link.pending[i]
                    break
            if txn is None:
                return          # unsolicited: it authorises nothing
            txn.reply = reply
            self._answered[txn.seq] = txn
            if len(self._answered) > 64:
                for old in sorted(self._answered)[:-64]:
                    del self._answered[old]
            if txn.seq in self._stop_seqs and reply.ok:
                self._stop_acked_seqs.add(txn.seq)
            if link is self._accel:
                self._on_accel_reply(txn, reply)
            else:
                self._on_drive_reply(txn, reply)

    def _on_accel_reply(self, txn: _Txn, r: p.Reply) -> None:
        if r.cmd == p.ACCEL_DUTY_CMD and not r.ok and r.data.upper() == "TIMEOUT":
            # AC 1.3: the board rested itself after host silence and holds a
            # latch until it sees an explicit zero. That silence is a fault
            # on our side; clear_faults() sends the zero.
            self._fault("accel board TIMEOUT: it rested itself after host silence", brake=False)
            return
        if r.cmd == p.ACCEL_INFO_CMD and r.ok:
            v = p.accel_version(r.data)
            if v:
                self._accel.firmware = v
        elif r.cmd == p.ACCEL_READ_CMD and r.ok:
            parts = r.data.split(";")
            try:
                duty = int(parts[0], 16); timeouts = int(parts[1], 16)
            except (ValueError, IndexError):
                return
            if not (0 <= duty <= 100 and 0 <= timeouts <= 255):
                return
            previous = self._accel_timeouts
            self._duty_read, self._accel_timeouts = duty, timeouts
            if previous is not None and timeouts > previous:
                self._fault("accel board took a timeout on its own (%d)" % timeouts, brake=False)
            elif self._duty_acked is not None and duty != self._duty_acked and self._duty_acked == self._duty_commanded:
                self._fault("accel board holds duty %d, host acknowledged %d" % (duty, self._duty_acked), brake=False)
        elif r.cmd == p.ACCEL_DUTY_CMD and r.ok:
            try:
                echoed = int(r.data, 16)
            except ValueError:
                return
            if txn.arg is None or echoed != txn.arg:
                return          # the board did not acknowledge what we sent
            self._duty_acked = echoed
            self._duty_acked_seq = txn.seq
            if echoed == 0:
                self._accel_alive = True

    def _on_drive_reply(self, txn: _Txn, r: p.Reply) -> None:
        if not r.ok:
            if (r.cmd == p.BRK_SW and txn.seq == self._brake_release_seq
                    and r.data.upper() == "AT_LIMIT"):
                # Seen on the vehicle on 13 Oct: a release asked of a brake
                # already at its released end is answered AT_LIMIT. That is
                # the released state, so it counts as the release ack.
                self._brake_applied = False
                self._brake_release_seq = None
                return
            if r.cmd in (p.READ_STEER, p.READ_BRAKE):
                # Seen on the vehicle on 13 Oct: 0x04;ERR;NO_SIGNAL after a
                # horn pulse. Feedback that fails is a fault, not a skip.
                self._fault("%s feedback failed: %s" % (
                    "steering" if r.cmd == p.READ_STEER else "brake", r.data or "ERR"))
            return
        if r.cmd == p.INFO:
            v = p.firmware_version(r.data)
            if v:
                self._drive.firmware = v
        elif r.cmd == p.STATUS:
            self._status_raw = r.data
        elif r.cmd == p.READ_STEER:
            a = p.angle_deg(r.data)
            if a is None:
                self._fault("steering feedback unreadable: %r" % r.data)
            elif not self._plausible(a, self._steer_angle, self._steer_limits, "steering"):
                return      # faulted; the last good reading stays
            else:
                self._steer_angle, self._steer_angle_at = a, self._now()
        elif r.cmd == p.READ_BRAKE:
            a = p.angle_deg(r.data)
            if a is None:
                self._fault("brake feedback unreadable: %r" % r.data)
            elif not self._plausible(a, self._brake_angle, None, "brake"):
                return
            else:
                self._brake_angle = a
        elif r.cmd == p.STR_LIM:
            self._steer_limits = p.limits_deg(r.data) or self._steer_limits
        elif r.cmd == p.BRK_LIM:
            self._brake_limits = p.limits_deg(r.data) or self._brake_limits
        elif r.cmd == p.BRK_SW and txn.seq == self._brake_release_seq:
            # the release frame itself was acknowledged. Acknowledged is not
            # physically released; the brake angle is in the snapshot for that.
            self._brake_applied = False
            self._brake_release_seq = None

    def _plausible(self, a: float, last: float | None, limits, what: str) -> bool:
        """A reading that jumps more than max_angle_step from the last good
        one, or (for steering) sits outside the board's own limits by more
        than 5 deg, is a sensor or supply fault, not a position."""
        if last is not None and abs(a - last) > self._max_angle_step:
            self._fault("%s feedback jumped %.1f to %.1f deg" % (what, last, a))
            return False
        if limits is not None and (a < limits[0] - 5.0 or a > limits[1] + 5.0):
            self._fault("%s feedback %.1f deg outside limits %s" % (what, a, limits))
            return False
        return True

    # -------------------------------------------------------------- writing

    def _write(self, link: _Link, frame: bytes, cmd: int, arg: int | None = None) -> int | None:
        """Write one frame as a transaction. Returns its seq, or None if
        it could not be written. A write that raises marks the port dead
        and stops through whatever is left."""
        with self._lock:
            if not link.connected:
                return None
            try:
                link.port.write(frame)
            except Exception as e:  # noqa: BLE001
                link.connected = False
                reason = "%s write failed (%s)" % (link.name, type(e).__name__)
                if reason not in self._faults:
                    self._faults.append(reason)
                if not self._in_stop:
                    self.safe_stop()
                return None
            self._seq += 1
            txn = _Txn(self._seq, cmd, arg, self._now())
            link.pending.append(txn)
        if self._on_tx_hook is not None:
            try:
                self._on_tx_hook(link.name, frame)
            except Exception:  # noqa: BLE001
                pass
        return txn.seq

    def _ask(self, link: _Link, frame: bytes, cmd: int, arg: int | None = None) -> p.Reply | None:
        seq = self._write(link, frame, cmd, arg)
        if seq is None:
            return None
        return self._await(seq)

    def _await(self, seq: int) -> p.Reply | None:
        """Block until transaction `seq` is answered or the reply timeout
        passes. Start and close only; never while driving."""
        deadline = self._now() + self._reply_timeout
        while self._now() < deadline:
            with self._lock:
                txn = self._answered.pop(seq, None)
                if txn is not None:
                    return txn.reply
                if not any(t.seq == seq for link in (self._drive, self._accel) for t in link.pending):
                    return None          # never written, or expired
            self._sleep(0.01)
            time.sleep(0.001)   # let the reader thread run under a fake clock
        with self._lock:
            for link in (self._drive, self._accel):
                link.pending = deque(t for t in link.pending if t.seq != seq)
        return None

    # ------------------------------------------------------------- commands

    def _check_open(self, what: str) -> None:
        if self._closing:
            raise Refused("%s refused: closing" % what)
        if self._faults:
            raise Refused("%s refused: faulted (%s)" % (what, "; ".join(self._faults)))
        if self._safe_stopped:
            raise Refused("%s refused: safe-stopped, clear_faults() first" % what)

    def heartbeat(self) -> None:
        """The command path above is alive. Feed this from every command
        frame, not from a separate heartbeat message."""
        with self._lock:
            self._last_heartbeat = self._now()

    def set_throttle(self, pct: int) -> None:
        pct = int(pct)
        if not 0 <= pct <= 100:
            raise ValueError("throttle must be 0 to 100, got %d" % pct)
        with self._lock:
            if pct > 0:
                self._check_open("throttle")
                if not self._drive.connected:
                    raise Refused("throttle refused: drive link down, brake unreachable")
                if not self._accel_alive:
                    raise Refused("throttle refused: accel board has not acknowledged duty zero")
                if self._brake_applied:
                    raise Refused("throttle refused: brake applied or not known released")
                pct = min(pct, self._max_duty)
            self._duty_commanded = pct
            seq = self._write(self._accel, p.accel_duty(pct), p.ACCEL_DUTY_CMD, arg=pct)
            if seq is not None:
                self._duty_last_seq = seq

    def brake(self, action: str) -> None:
        frame = p.brake(action)
        with self._lock:
            if action == "apply":
                # throttle off before the brake moves, and locked even if
                # the accelerator write fails
                self._brake_applied = True
                self._brake_release_seq = None
                self._duty_commanded = 0
                seq = self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD, arg=0)
                if seq is not None:
                    self._duty_last_seq = seq
                self._brake_moving = True
                self._write(self._drive, frame, p.BRK_SW, arg=0x01)
            elif action == "release":
                self._check_open("brake release")
                self._brake_moving = True
                seq = self._write(self._drive, frame, p.BRK_SW, arg=0x02)
                self._brake_release_seq = seq
            else:
                self._brake_moving = False
                self._write(self._drive, frame, p.BRK_SW, arg=0x00)

    def steer(self, direction: str) -> None:
        frame = p.steer(direction)
        with self._lock:
            if direction != "stop":
                self._check_open("steer")
                at = self._steer_angle_at
                if at is None or self._now() - at > self._feedback_max_age:
                    raise Refused("steer refused: no fresh steering reading")
            self._steer_target = None
            self._steer_moving = direction
            self._write(self._drive, frame, p.STR_SW, arg=p._STEER[direction])

    def steer_to(self, angle_deg: float) -> None:
        """Closed loop on the steering angle reading, driven by tick().
        Needs the sense (which direction raises the reading) from the
        bench, and the limits from the board."""
        angle_deg = float(angle_deg)
        if not math.isfinite(angle_deg):
            raise ValueError("steer_to needs a finite angle")
        with self._lock:
            self._check_open("steer_to")
            if self._steer_sense is None:
                raise Refused("steer_to refused: steering sense not known, set it from the bench")
            if self._steer_limits is None:
                raise Refused("steer_to refused: steering limits not read")
            lo, hi = self._steer_limits
            self._steer_target = max(lo, min(hi, angle_deg))

    def gear(self, g: str) -> None:
        frame = p.gear(g)
        with self._lock:
            self._check_open("gear")
            zero_acked = (self._duty_commanded == 0 and self._duty_acked == 0
                          and self._duty_acked_seq is not None
                          and self._duty_acked_seq == self._duty_last_seq)
            if not zero_acked:
                raise Refused("gear refused: latest throttle zero not acknowledged")
            self._write(self._drive, frame, p.GEAR, arg=p._GEAR[g])
            self._commanded["gear"] = g

    def speed_mode(self, mode: int) -> None:
        frame = p.speed_mode(mode)
        with self._lock:
            self._check_open("speed mode")
            self._write(self._drive, frame, p.SPEED, arg=mode)
            self._commanded["speed_mode"] = mode

    def light(self, which: str) -> None:
        frame = p.light(which)
        with self._lock:
            if self._closing:
                raise Refused("light refused: closing")
            self._write(self._drive, frame, p.LIGHT, arg=p._LIGHT[which])
            self._commanded["light"] = which

    def indicator(self, which: str) -> None:
        frame = p.indicator(which)
        with self._lock:
            if self._closing:
                raise Refused("indicator refused: closing")
            self._write(self._drive, frame, p.IND, arg=p._IND[which])
            self._commanded["indicator"] = which

    def horn(self) -> None:
        with self._lock:
            if self._closing:
                raise Refused("horn refused: closing")
            self._write(self._drive, p.horn(), p.HORN, arg=0x01)

    def read_accel(self) -> None:
        """AC 1.3 read-back (0x03): duty the board holds and its timeout
        count, into snapshot()["accel"]["duty_read"/"timeouts"]. On AC 1.2
        the board answers ERR;UNKNOWN_COMMAND, which is ignored."""
        with self._lock:
            if not self._accel_read_back:
                return
            self._write(self._accel, p.accel_read(), p.ACCEL_READ_CMD)

    def read_status(self) -> None:
        """Ask the drive board for its switch states (0x16). The reply
        lands in snapshot()["drive"]["status_raw"]. A read, not a move."""
        with self._lock:
            self._write(self._drive, p.status(), p.STATUS)

    # ----------------------------------------------------------- supervision

    def safe_stop(self, *, brake: bool | None = None) -> None:
        """Propulsion off, then brake on (if brake_on_stop), then steering
        stopped. Each step is attempted whatever happened to the one
        before. Idempotent. Cannot act through a link that is down; the
        stop report says what was acknowledged."""
        with self._lock:
            if self._in_stop:
                return
            self._in_stop = True
            try:
                self._safe_stopped = True
                self._stop_requested = True
                self._stop_seqs = set()
                self._stop_acked_seqs = set()
                self._steer_target = None
                self._steer_moving = "stop"
                self._duty_commanded = 0
                self._brake_release_seq = None
                seqs = [self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD, arg=0)]
                if seqs[0] is not None:
                    self._duty_last_seq = seqs[0]
                use_brake = (self._brake_on_stop if brake is None else brake) and not self._board_tripped
                if use_brake:
                    self._brake_applied = True
                    self._brake_moving = True
                    seqs.append(self._write(self._drive, p.brake("apply"), p.BRK_SW, arg=0x01))
                else:
                    # the brake stroke is not characterised: halt the actuator
                    # where it is rather than drive it to an unknown end
                    self._brake_moving = False
                    seqs.append(self._write(self._drive, p.brake("stop"), p.BRK_SW, arg=0x00))
                seqs.append(self._write(self._drive, p.steer("stop"), p.STR_SW, arg=0x00))
                self._stop_seqs = {s for s in seqs if s is not None}
                self._stop_incomplete = any(s is None for s in seqs)
            finally:
                self._in_stop = False

    _stop_incomplete = False

    def clear_faults(self) -> None:
        """A human decided the links are back and the vehicle is safe.
        Clears the latch; manufactures no acknowledgement. Throttle still
        needs a fresh duty-zero acknowledgement."""
        with self._lock:
            self._faults.clear()
            self._board_tripped = False
            self._safe_stopped = False
            self._stop_requested = False
            self._stop_seqs = set()
            self._stop_acked_seqs = set()
            self._stop_incomplete = False
            self._accel_alive = False
            seq = self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD, arg=0)
            if seq is not None:
                self._duty_last_seq = seq

    def _fault(self, reason: str, link: _Link | None = None, *, port_dead: bool = False,
               brake: bool | None = None) -> None:
        """Record a fault and stop. A silent board keeps its port open and
        still gets the stop frames; a port that raised is marked dead
        first so nothing blocks on it."""
        with self._lock:
            if link is not None:
                link.answering = False
                if port_dead:
                    link.connected = False
            if reason not in self._faults:
                self._faults.append(reason)
            if brake is False:
                self._board_tripped = True
            self.safe_stop(brake=brake)

    def tick(self) -> None:
        """Call at rate (the owner's tick thread). Polls, checks reply
        deadlines, the heartbeat, and drives the steering loop."""
        with self._lock:
            if not self._started:
                return
            now = self._now()
            # 1. reply deadlines on both links
            for link in (self._accel, self._drive):
                if link.pending and now - link.pending[0].sent_at > self._reply_timeout:
                    link.pending.clear()
                    if link is self._accel:
                        self._accel_alive = False
                    self._fault("%s board not answering" % link.name, link)
            # 2. host heartbeat while motion is commanded
            motion = (self._duty_commanded > 0 or self._steer_moving != "stop"
                      or self._steer_target is not None or self._brake_moving)
            if motion and not self._safe_stopped:
                hb = self._last_heartbeat
                if hb is None or now - hb > self._hb_timeout:
                    self.safe_stop()
            # 3. accelerator liveness, and the keepalive AC 1.3 needs while
            #    the throttle is on: a probe at least every accel_probe_s
            if self._accel.connected:
                last = self._accel.last_reply_at or 0.0
                probe = self._last_accel_probe_at or 0.0
                due = now - probe >= self._accel_probe_s and (
                    self._duty_commanded > 0 or (not self._accel.pending and now - last > self._accel_probe_s))
                if due:
                    self._last_accel_probe_at = now
                    if self._accel_read_back:
                        self._write(self._accel, p.accel_read(), p.ACCEL_READ_CMD)
                    else:
                        self._write(self._accel, p.accel_info(), p.ACCEL_INFO_CMD)
            # 4. drive polls
            if self._poll_period is not None and self._drive.connected:
                if self._last_poll_at is None or now - self._last_poll_at >= self._poll_period:
                    self._last_poll_at = now
                    self._write(self._drive, p.read_steer(), p.READ_STEER)
                    self._write(self._drive, p.read_brake(), p.READ_BRAKE)
            # 5. steering loop
            self._steer_loop(now)

    def _steer_loop(self, now: float) -> None:
        target = self._steer_target
        if target is None or self._safe_stopped or self._faults:
            return
        angle, at = self._steer_angle, self._steer_angle_at
        fresh = angle is not None and at is not None and now - at <= self._feedback_max_age
        if not fresh:
            # no fresh reading, no move: stop and drop the target
            self._steer_target = None
            if self._steer_moving != "stop":
                self._steer_moving = "stop"
                self._write(self._drive, p.steer("stop"), p.STR_SW, arg=0x00)
            return
        err = target - angle
        if abs(err) <= self._deadband:
            if self._steer_moving != "stop":
                self._steer_moving = "stop"
                self._write(self._drive, p.steer("stop"), p.STR_SW, arg=0x00)
            self._steer_target = None
            return
        increases_right = self._steer_sense == "right_increases"
        want = "right" if (err > 0) == increases_right else "left"
        if self._steer_moving != want:
            self._steer_moving = want
            self._write(self._drive, p.steer(want), p.STR_SW, arg=p._STEER[want])

    # ------------------------------------------------------------- telemetry

    def snapshot(self) -> dict:
        with self._lock:
            now = self._now()
            def age(t):
                return None if t is None else round(now - t, 3)
            stop_acked = (self._stop_requested and not self._stop_incomplete
                          and bool(self._stop_seqs)
                          and self._stop_seqs <= self._stop_acked_seqs)
            return {
                "drive": {
                    "firmware": self._drive.firmware,
                    "connected": self._drive.connected,
                    "answering": self._drive.answering,
                    "last_reply_age_s": age(self._drive.last_reply_at),
                    "status_raw": self._status_raw,
                },
                "accel": {
                    "firmware": self._accel.firmware,
                    "connected": self._accel.connected,
                    "answering": self._accel.answering,
                    "alive": self._accel_alive,
                    "duty_commanded": self._duty_commanded,
                    "duty_acked": self._duty_acked,
                    "duty_read": self._duty_read,
                    "timeouts": self._accel_timeouts,
                    "read_back": self._accel_read_back,
                    "last_reply_age_s": age(self._accel.last_reply_at),
                },
                "steer": {
                    "angle_deg": self._steer_angle,
                    "angle_age_s": age(self._steer_angle_at),
                    "limits_deg": self._steer_limits,
                    "target_deg": self._steer_target,
                    "moving": self._steer_moving,
                    "sense": self._steer_sense,
                },
                "brake": {
                    "angle_deg": self._brake_angle,
                    "limits_deg": self._brake_limits,
                    "applied": self._brake_applied,
                },
                "commanded": dict(self._commanded),
                "safe_stopped": self._safe_stopped,
                "faults": list(self._faults),
                "stop": {"requested": self._stop_requested, "acked": bool(stop_acked)},
            }


def _name(link: _Link) -> str:
    return getattr(link.port, "device", link.name)
