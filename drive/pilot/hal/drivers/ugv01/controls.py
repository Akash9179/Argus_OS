"""The one owner of ugv-01's two boards, and every safety rule about them.

Two boards, two ports, one object. Nothing else in ARGUS writes to either
port. The teleop bridge adapter and the HAL locomotion driver both sit on
top of this class (ADR-0009: the hardware is driven from exactly one
place).

What this class guarantees, and what it cannot:

- It starts inhibited and unknown. Open is treated as a reset. It asks
  both boards who they are and reads the drive board's state before any
  actuator frame is allowed. Throttle is refused until the accelerator
  board has acknowledged duty zero, and until the brake is known released.
- It never sends a locked, admin, reset, Wi-Fi or limit-write command
  (protocol.py has no encoder for them). It never auto-centres steering:
  that is a move, not a stop.
- Every accelerator frame must be answered by a reply to that frame
  within `reply_timeout_s`; a quiet board gets a liveness probe every
  `accel_probe_s`. The drive board's health is its reply deadline on the
  angle poll, not whether a port is open.
- A host heartbeat (`heartbeat()`, fed by the command path above) that
  goes silent for `heartbeat_timeout_s` while motion is commanded, or any
  board fault, triggers `safe_stop()`: accelerator duty zero first, then
  brake apply, then steering stop. Faults latch; reconnecting a link does
  not clear them, `clear_faults()` after a human decision does.
- Brake apply zeroes the throttle first and locks it; a failed accelerator
  write never stops the brake frame being sent. A gear change needs an
  acknowledged duty zero.

What it cannot guarantee, stated so nobody reads more into it: a host
cannot command a board through a link that has failed. If the
accelerator's link dies with duty above zero, this class cannot zero it;
if the drive link dies, this class cannot apply the brake. Neither
board's firmware is known to have a watchdog. Until that is proven or
built, `snapshot()["stop_confirmed"]` is False after any fault, and the
hardware safety gate in ARCHITECTURE.md section 6 stays shut.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from pilot.hal.drivers.ugv01 import protocol as p
from pilot.hal.drivers.ugv01.link import Port


class LinkError(RuntimeError):
    """A board did not answer when it had to."""


class Refused(RuntimeError):
    """A command was not sent, and the reason is in the message."""


STEER_SENSES = ("right_increases", "left_increases")


@dataclass
class _Link:
    name: str
    port: Port
    connected: bool = False      # port open and no write has failed
    answering: bool = False      # replies arriving within the deadline
    firmware: str | None = None
    last_reply_at: float | None = None
    pending: deque = field(default_factory=deque)   # (cmd, sent_at)
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
        accel_probe_s: float = 0.5,
        max_duty: int = 90,
        poll_hz: float = 5.0,
        steer_sense: str | None = None,
        steer_deadband_deg: float = 1.0,
        on_line=None,
    ) -> None:
        """`on_line(link_name, line)` sees every decoded line from either
        board, for the bench log. It runs on the reader thread."""
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
        self._max_duty = max_duty
        self._poll_period = (1.0 / poll_hz) if poll_hz > 0 else None
        self._steer_sense = steer_sense
        self._deadband = steer_deadband_deg
        self._on_line_hook = on_line

        self._lock = threading.RLock()
        self._drive = _Link("drive", drive_port)
        self._accel = _Link("accel", accel_port)
        self._started = False

        # drive board state, from replies
        self._status_raw: str | None = None
        self._steer_angle: float | None = None
        self._steer_angle_at: float | None = None
        self._brake_angle: float | None = None
        self._steer_limits: tuple[float, float] | None = None
        self._brake_limits: tuple[float, float] | None = None
        # intent and acknowledgement
        self._brake_applied: bool = True      # unknown counts as applied
        self._accel_alive = False             # duty zero acknowledged since open
        self._duty_commanded = 0
        self._duty_acked: int | None = None
        self._steer_moving: str = "stop"
        self._steer_target: float | None = None
        self._commanded = {"gear": None, "light": None, "indicator": None, "speed_mode": None}
        # supervision
        self._last_heartbeat: float | None = None
        self._last_poll_at: float | None = None
        self._last_accel_probe_at: float | None = None
        self._safe_stopped = False
        self._faults: list[str] = []
        self._stop_confirmed = True

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Open both boards, ask who they are, read the drive board's
        state. Sends no actuator frame. Raises LinkError and closes
        everything if either board stays silent."""
        with self._lock:
            if self._started:
                return
        # not under the lock: the reader threads need it to deliver the
        # replies this sequence waits for
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
        self._send(d, p.info(), p.INFO)
        if not self._await(d, p.INFO):
            raise LinkError("drive board did not answer INFO on %s" % _name(d))
        for frame, cmd in ((p.status(), p.STATUS), (p.read_steer_limits(), p.STR_LIM),
                           (p.read_brake_limits(), p.BRK_LIM), (p.read_steer(), p.READ_STEER),
                           (p.read_brake(), p.READ_BRAKE)):
            self._send(d, frame, cmd)
            self._await(d, cmd)

    def _open_accel(self) -> None:
        a = self._accel
        a.port.open()
        a.connected = True
        a.stop.clear()
        a.thread = threading.Thread(target=self._reader, args=(a,), daemon=True,
                                    name="ugv01-accel-reader")
        a.thread.start()
        self._sleep(self._accel_boot_s)           # the board reboots on open
        self._send(a, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD)
        self._duty_commanded = 0
        if not self._await(a, p.ACCEL_DUTY_CMD):
            raise LinkError("accelerator board did not acknowledge duty zero on %s" % _name(a))
        self._send(a, p.accel_info(), p.ACCEL_INFO_CMD)
        self._await(a, p.ACCEL_INFO_CMD)

    def close(self) -> None:
        """Stop first, then let go. Closing a port may reset the board
        behind it; that is not relied on for anything."""
        with self._lock:
            started = self._started
            self._started = False
        if started:
            self.safe_stop()
            self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD)
        self._close_ports()

    def _close_ports(self) -> None:
        for link in (self._accel, self._drive):
            link.stop.set()
            link.connected = False
            try:
                link.port.close()
            except Exception:
                pass

    # -------------------------------------------------------------- readers

    def _reader(self, link: _Link) -> None:
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
            line = p.decode_line(raw)
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
            if reply is None:
                return
            # acknowledge exactly the frame this reply answers
            for i, (cmd, _sent) in enumerate(link.pending):
                if cmd == reply.cmd:
                    del link.pending[i]
                    break
            if link is self._accel:
                self._on_accel_reply(reply)
            else:
                self._on_drive_reply(reply)

    def _on_accel_reply(self, r: p.Reply) -> None:
        if r.cmd == p.ACCEL_INFO_CMD and r.ok:
            self._accel.firmware = p.accel_version(r.data)
        elif r.cmd == p.ACCEL_DUTY_CMD and r.ok:
            try:
                self._duty_acked = int(r.data, 16)
            except ValueError:
                return
            if self._duty_acked == 0:
                self._accel_alive = True

    def _on_drive_reply(self, r: p.Reply) -> None:
        if r.cmd == p.INFO and r.ok:
            self._drive.firmware = p.firmware_version(r.data)
        elif r.cmd == p.STATUS and r.ok:
            self._status_raw = r.data
        elif r.cmd == p.READ_STEER and r.ok:
            a = p.angle_deg(r.data)
            if a is not None:
                self._steer_angle, self._steer_angle_at = a, self._now()
        elif r.cmd == p.READ_BRAKE and r.ok:
            a = p.angle_deg(r.data)
            if a is not None:
                self._brake_angle = a
        elif r.cmd == p.STR_LIM and r.ok:
            self._steer_limits = p.limits_deg(r.data) or self._steer_limits
        elif r.cmd == p.BRK_LIM and r.ok:
            self._brake_limits = p.limits_deg(r.data) or self._brake_limits
        elif r.cmd == p.BRK_SW and r.ok and self._brake_release_pending:
            # the release frame was acknowledged: the brake is no longer
            # commanded on. Acknowledged is not the same as physically
            # released; the brake angle is in the snapshot for that.
            self._brake_applied = False
            self._brake_release_pending = False

    _brake_release_pending = False

    # -------------------------------------------------------------- writing

    def _send(self, link: _Link, frame: bytes, cmd: int) -> bool:
        """Write one frame and remember that it awaits a reply."""
        return self._write(link, frame, cmd)

    def _write(self, link: _Link, frame: bytes, cmd: int) -> bool:
        with self._lock:
            if not link.connected:
                return False
            try:
                link.port.write(frame)
            except Exception as e:  # noqa: BLE001
                # the port is gone: say so, do not try to stop through it
                link.connected = False
                reason = "%s write failed (%s)" % (link.name, type(e).__name__)
                if reason not in self._faults:
                    self._faults.append(reason)
                self._stop_confirmed = False
                return False
            link.pending.append((cmd, self._now()))
            return True

    def _await(self, link: _Link, cmd: int) -> bool:
        """Block until the reply for `cmd` arrives or the reply timeout
        passes. Used only during start; never while driving."""
        deadline = self._now() + self._reply_timeout
        while self._now() < deadline:
            with self._lock:
                if all(c != cmd for c, _ in link.pending):
                    return True
            self._sleep(0.01)
            time.sleep(0.001)   # let the reader thread run under a fake clock
        with self._lock:
            link.pending = deque((c, t) for c, t in link.pending if c != cmd)
        return False

    # ------------------------------------------------------------- commands

    def heartbeat(self) -> None:
        """The command path above is alive. Feed this from every command
        frame, not from a separate heartbeat message."""
        with self._lock:
            self._last_heartbeat = self._now()

    def set_throttle(self, pct: int) -> None:
        pct = int(pct)
        with self._lock:
            if pct > 0:
                if self._faults:
                    raise Refused("throttle refused: faulted (%s)" % "; ".join(self._faults))
                if self._safe_stopped:
                    raise Refused("throttle refused: safe-stopped, clear_faults() first")
                if not self._drive.connected:
                    raise Refused("throttle refused: drive link down, brake unreachable")
                if not self._accel_alive:
                    raise Refused("throttle refused: accel board has not acknowledged duty zero")
                if self._brake_applied:
                    raise Refused("throttle refused: brake applied or not known released")
                pct = min(pct, self._max_duty)
            self._duty_commanded = pct
            self._write(self._accel, p.accel_duty(pct), p.ACCEL_DUTY_CMD)

    def brake(self, action: str) -> None:
        frame = p.brake(action)
        with self._lock:
            if action == "apply":
                # throttle off before the brake moves, and locked even if
                # the accelerator write fails
                self._brake_applied = True
                self._brake_release_pending = False
                self._duty_commanded = 0
                self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD)
            elif action == "release":
                if self._faults or self._safe_stopped:
                    raise Refused("brake release refused: faulted or safe-stopped")
                self._brake_release_pending = True
            self._write(self._drive, frame, p.BRK_SW)

    def steer(self, direction: str) -> None:
        frame = p.steer(direction)
        with self._lock:
            if direction != "stop" and (self._faults or self._safe_stopped):
                raise Refused("steer refused: faulted or safe-stopped")
            self._steer_target = None
            self._steer_moving = direction
            self._write(self._drive, frame, p.STR_SW)

    def steer_to(self, angle_deg: float) -> None:
        """Closed loop on the steering angle reading, driven by tick().
        Needs the sense (which direction raises the reading) to be known
        from the bench, and the limits from the board."""
        with self._lock:
            if self._steer_sense is None:
                raise Refused("steer_to refused: steering sense not known, set it from the bench")
            if self._steer_limits is None:
                raise Refused("steer_to refused: steering limits not read")
            lo, hi = self._steer_limits
            self._steer_target = max(lo, min(hi, float(angle_deg)))

    def gear(self, g: str) -> None:
        frame = p.gear(g)
        with self._lock:
            if self._duty_acked not in (0,) or self._duty_commanded != 0:
                raise Refused("gear refused: throttle not acknowledged at zero")
            self._write(self._drive, frame, p.GEAR)
            self._commanded["gear"] = g

    def speed_mode(self, mode: int) -> None:
        frame = p.speed_mode(mode)
        with self._lock:
            self._write(self._drive, frame, p.SPEED)
            self._commanded["speed_mode"] = mode

    def light(self, which: str) -> None:
        frame = p.light(which)
        with self._lock:
            self._write(self._drive, frame, p.LIGHT)
            self._commanded["light"] = which

    def indicator(self, which: str) -> None:
        frame = p.indicator(which)
        with self._lock:
            self._write(self._drive, frame, p.IND)
            self._commanded["indicator"] = which

    def horn(self) -> None:
        with self._lock:
            self._write(self._drive, p.horn(), p.HORN)

    # ----------------------------------------------------------- supervision

    def safe_stop(self) -> None:
        """Propulsion off, then brake on, then steering stopped. Each
        step is attempted whatever happened to the one before. Idempotent.
        Does not depend on either link being up, and cannot act through a
        link that is down: that is recorded, not hidden."""
        with self._lock:
            self._safe_stopped = True
            self._steer_target = None
            self._steer_moving = "stop"
            self._duty_commanded = 0
            self._brake_applied = True
            self._brake_release_pending = False
            ok = self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD)
            ok = self._write(self._drive, p.brake("apply"), p.BRK_SW) and ok
            ok = self._write(self._drive, p.steer("stop"), p.STR_SW) and ok
            self._stop_confirmed = ok and not self._faults

    def clear_faults(self) -> None:
        """A human decided the links are back and the vehicle is safe.
        Re-reads nothing; the next tick's polls do. Throttle still needs
        a fresh duty-zero acknowledgement."""
        with self._lock:
            self._faults.clear()
            self._safe_stopped = False
            self._stop_confirmed = True
            self._accel_alive = False
            self._write(self._accel, p.ACCEL_ZERO, p.ACCEL_DUTY_CMD)

    def _fault(self, reason: str, link: _Link | None = None, *, port_dead: bool = False) -> None:
        """Record a fault and stop. A board that is silent keeps its port
        open and still gets the stop frames; a port that raised is marked
        dead first so nothing blocks on it."""
        with self._lock:
            if link is not None:
                link.answering = False
                if port_dead:
                    link.connected = False
            if reason not in self._faults:
                self._faults.append(reason)
            self.safe_stop()

    def tick(self) -> None:
        """Call at rate (the owner's tick thread). Polls, checks reply
        deadlines, the heartbeat, and drives the steering loop."""
        with self._lock:
            if not self._started:
                return
            now = self._now()
            # 1. reply deadlines on both links
            for link in (self._accel, self._drive):
                if link.pending and now - link.pending[0][1] > self._reply_timeout:
                    link.pending.clear()
                    if link is self._accel:
                        self._accel_alive = False
                    self._fault("%s board not answering" % link.name, link)
            # 2. host heartbeat while motion is commanded
            motion = self._duty_commanded > 0 or self._steer_moving != "stop" \
                or self._steer_target is not None
            if motion and not self._safe_stopped:
                hb = self._last_heartbeat
                if hb is None or now - hb > self._hb_timeout:
                    self.safe_stop()
            # 3. accelerator liveness: a quiet board gets asked
            if self._accel.connected and not self._accel.pending:
                last = self._accel.last_reply_at or 0.0
                probe = self._last_accel_probe_at or 0.0
                if now - last > self._accel_probe_s and now - probe > self._accel_probe_s:
                    self._last_accel_probe_at = now
                    self._write(self._accel, p.accel_info(), p.ACCEL_INFO_CMD)
            # 4. drive polls
            if self._poll_period is not None and self._drive.connected:
                if self._last_poll_at is None or now - self._last_poll_at >= self._poll_period:
                    self._last_poll_at = now
                    self._write(self._drive, p.read_steer(), p.READ_STEER)
                    self._write(self._drive, p.read_brake(), p.READ_BRAKE)
            # 5. steering loop
            self._steer_loop()

    def _steer_loop(self) -> None:
        target = self._steer_target
        if target is None or self._safe_stopped or self._faults:
            return
        angle = self._steer_angle
        if angle is None:
            return
        err = target - angle
        if abs(err) <= self._deadband:
            if self._steer_moving != "stop":
                self._steer_moving = "stop"
                self._write(self._drive, p.steer("stop"), p.STR_SW)
            self._steer_target = None
            return
        increases_right = self._steer_sense == "right_increases"
        want = "right" if (err > 0) == increases_right else "left"
        if self._steer_moving != want:
            self._steer_moving = want
            self._write(self._drive, p.steer(want), p.STR_SW)

    # ------------------------------------------------------------- telemetry

    def snapshot(self) -> dict:
        with self._lock:
            now = self._now()
            def age(t):
                return None if t is None else round(now - t, 3)
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
                "stop_confirmed": self._stop_confirmed,
            }


def _name(link: _Link) -> str:
    return getattr(link.port, "device", link.name)
