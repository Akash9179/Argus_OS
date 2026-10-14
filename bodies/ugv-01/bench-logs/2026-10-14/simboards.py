"""Real-time simulators of ugv-01's two boards with the watchdog firmware,
behind the same Port protocol the controls use, so tonight's runner can be
exercised on a laptop before it touches the vehicle.

  python3 simboards.py [--broken accel|drive|both] -- <bench_run.py args>

The runner is executed with PySerialPort replaced: device "drive" is the
simulated 4.1.5 drive module, "accel" the simulated AC 1.3 Nano.
--broken makes that board's watchdog never fire (AC 1.2 / 4.1.4 behaviour)
so the runner's FAIL path and the host's fallback stop are exercised.
"""
import argparse, queue, runpy, sys, threading, time

SPEED = 67.0        # deg/s steering, measured 13 Oct
BRK_SPEED = 95.0


class SimPort:
    def __init__(self, board):
        self.board = board
        self.rx: queue.Queue[bytes] = queue.Queue()
        self.is_open = False
        self.device = board.name

    def open(self):
        self.board.reset(self)
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, data: bytes):
        if not self.is_open:
            raise OSError("port closed")
        self.board.tick(time.monotonic())
        for line in self.board.handle(data.decode("ascii", "replace").strip(), time.monotonic()):
            self.rx.put(line.encode() + b"\n")

    def readline(self) -> bytes:
        self.board.tick(time.monotonic())
        try:
            return self.rx.get(timeout=0.05)
        except queue.Empty:
            return b""


class Nano13:
    name = "accel"

    def __init__(self, broken=False):
        self.broken = broken
        self.lock = threading.Lock()

    def reset(self, port):
        with self.lock:
            self.port = port
            self.duty = 0; self.timeouts = 0; self.latched = False
            self.last_valid = time.monotonic()
            self.boot_at = time.monotonic()
            self.events = []

    def tick(self, now):
        with self.lock:
            if self.broken:
                return
            if self.duty > 0 and now - self.last_valid > 0.8:
                self.duty = 0; self.timeouts += 1; self.latched = True
                self.events.append(("rest", now))
                print("[sim accel] RESTED on its own at %.3f" % now, flush=True)

    def handle(self, text, now):
        with self.lock:
            if now - self.boot_at < 2.0:
                return []                   # rebooting after DTR
            if text == "0x01":
                self.last_valid = now
                return ["0x01;OK;AC0103"]
            if text == "0x03":
                self.last_valid = now
                return ["0x03;OK;%02X;%02X" % (self.duty, min(self.timeouts, 255))]
            if text.startswith("0x02;"):
                try:
                    d = int(text.split(";")[1], 16)
                except ValueError:
                    return ["0x02;ERR;INVALID_DUTY"]
                if d > 100:
                    return ["0x02;ERR;INVALID_DUTY"]
                self.last_valid = now
                if d == 0:
                    self.duty = 0; self.latched = False
                    return ["0x02;OK;00"]
                if self.latched:
                    return ["0x02;ERR;TIMEOUT"]
                self.duty = d
                print("[sim accel] DRIVING at %d%%" % d, flush=True)
                return ["0x02;OK;%02X" % d]
            return ["ERR;UNKNOWN_COMMAND"]


class Drive415:
    name = "drive"

    def __init__(self, broken=False):
        self.broken = broken
        self.lock = threading.Lock()

    def reset(self, port):
        with self.lock:
            self.port = port
            self.steer = 153.7; self.brake = 61.7
            self.steer_dir = 0; self.brake_dir = 0
            self.gear = 3; self.wd = 0; self.latched = False
            self.last_accepted = time.monotonic(); self.last_tick = time.monotonic()
            self.lim = (67.0, 243.0); self.blim = (70.0, 170.0)

    def _move(self, now):
        dt = now - self.last_tick; self.last_tick = now
        if self.steer_dir:
            self.steer += (SPEED * dt) * (1 if self.steer_dir == 1 else -1)
            if self.steer >= self.lim[1] or self.steer <= self.lim[0]:
                self.steer = max(self.lim[0], min(self.lim[1], self.steer))
                self.steer_dir = 0
                print("[sim drive] steering LIMIT STOP at %.1f" % self.steer, flush=True)
        if self.brake_dir:
            self.brake += (BRK_SPEED * dt) * (1 if self.brake_dir == 1 else -1)
            if self.brake <= 61.7: self.brake = 61.7; self.brake_dir = 0
            if self.brake >= 170.0: self.brake = 170.0; self.brake_dir = 0

    def tick(self, now):
        with self.lock:
            self._move(now)
            if self.broken:
                return
            if (self.steer_dir or self.brake_dir) and now - self.last_accepted > 0.8:
                self.steer_dir = 0; self.brake_dir = 0; self.wd += 1; self.latched = True
                print("[sim drive] WD TIMEOUT on its own at %.3f, steer %.1f" % (now, self.steer), flush=True)
                self.port.rx.put(b"0x00;WD;TIMEOUT\n")

    def handle(self, text, now):
        with self.lock:
            self._move(now)
            parts = text.split()
            try:
                cmd = int(parts[0], 16)
            except ValueError:
                return ["0x00;ERR;BAD_CMD"]
            arg = int(parts[1], 16) if len(parts) > 1 else None
            def ok(data=None):
                self.last_accepted = now
                return ["0x%02X;OK%s" % (cmd, (";" + data) if data is not None else "")]
            if cmd == 0x01: return ok("040105")
            if cmd == 0x16:
                return ok("A=00,ST=%02X,BR=%02X,SP=02,GR=%02X,LI=00,IN=00,HO=00,WI=00,CT=00,WD=%02X"
                          % (self.steer_dir, self.brake_dir, self.gear, min(self.wd, 255)))
            if cmd == 0x04: return ok("%04X" % int(round(self.steer * 10)))
            if cmd == 0x03: return ok("%04X" % int(round(self.brake * 10)))
            if cmd == 0x10: return ok("029E097E")
            if cmd == 0x0F: return ok("02BC06A4")
            if cmd == 0x08:
                self.gear = arg; return ok("%02X" % arg)
            if cmd == 0x05:
                if arg == 0:
                    self.steer_dir = 0; self.latched = False; return ok("00")
                if self.latched: return ["0x05;ERR;WD_TRIPPED"]
                self.steer_dir = arg
                print("[sim drive] steering %s from %.1f" % ("LEFT" if arg == 1 else "RIGHT", self.steer), flush=True)
                return ok("%02X" % arg)
            if cmd == 0x06:
                if arg == 0:
                    self.brake_dir = 0; self.latched = False; return ok("00")
                if self.latched: return ["0x06;ERR;WD_TRIPPED"]
                if arg == 2 and self.brake <= 61.7: return ["0x06;ERR;AT_LIMIT"]
                self.brake_dir = 1 if arg == 1 else -1
                return ok("%02X" % arg)
            if cmd in (0x09, 0x0A, 0x0B, 0x07):
                return ok("%02X" % (arg or 0))
            return ["0x%02X;ERR;UNKNOWN" % cmd]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broken", choices=["accel", "drive", "both"], default=None)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--runner", required=True)
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    sys.path.insert(0, a.repo + "/drive")
    import pilot.hal.drivers.ugv01.link as link
    boards = {"drive": Drive415(broken=a.broken in ("drive", "both")),
              "accel": Nano13(broken=a.broken in ("accel", "both"))}
    link.PySerialPort = lambda device, *x, **k: SimPort(boards[device])
    rest = a.rest[1:] if a.rest and a.rest[0] == "--" else a.rest
    sys.argv = [a.runner] + rest
    t0 = time.monotonic()
    try:
        runpy.run_path(a.runner, run_name="__main__")
        code = 0
    except SystemExit as e:
        code = e.code
    print("[sim] runner exit code", code, "after %.1f s" % (time.monotonic() - t0), flush=True)
    for name, b in boards.items():
        print("[sim] %s final: %s" % (name, {k: v for k, v in vars(b).items() if k in ("duty", "timeouts", "latched", "steer", "steer_dir", "wd", "brake_dir")}), flush=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
