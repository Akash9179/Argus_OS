"""ugv-01 bench: one bounded command at a time, a human at the key, every
frame and every word kept.

    .venv/bin/python -m pilot.hal.drivers.ugv01.bench \\
        --drive /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \\
        --accel /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A5069RR4-if00-port0

Rule zero applies. The tool refuses to open a port until the operator has
typed the five preconditions back. Opening a port may reset a board.

What the tool sends on its own, so nobody is surprised:
  on open      INFO, STATUS, limits and angles to the drive board; duty
               zero then INFO to the throttle board. No actuator moves.
  on a fault   duty zero and steering stop. Brake apply only with
               --brake-on-stop, after the brake stroke has been seen.
  on quit      the same stop, then the ports close.

Every actuator command is a bounded pulse: it is shown first, sent only
after "go", stopped by the tool after its duration (default 300 ms for
steering and brake, 1000 ms for throttle), and only then does the tool
ask what the human saw. Typing `safe` at ANY prompt sends the stop at
once, before anything else happens. The host heartbeat is fed by this
tool's own tick thread; the human at the ignition key is the watchdog.

Commands:
  snap                               the controls snapshot
  steer left|right [ms]              pulse, auto-stop after ms
  steer stop                         stop now
  steer_to <deg>                     closed loop (needs --steer-sense)
  brake apply|release [ms]           pulse, auto-stop after ms
  brake stop                         stop now
  throttle <0-100> [ms]              duty pulse, back to zero after ms
  gear D|N|R   speed 1|2|3   light off|ring|high|low   ind off|left|right|park   horn
  safe                               stop now (also works at any prompt)
  clear                              clear latched faults (a human decision)
  note <text>                        a line for the log
  quit                               stop, close, exit
"""
from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import threading
import time
from datetime import datetime, timezone

from pilot.hal.drivers.ugv01.controls import LinkError, Refused, Ugv01Controls
from pilot.hal.drivers.ugv01.link import PySerialPort

PRECONDITIONS = [
    "drive wheels off the ground, on stands",
    "drive power isolated if this test allows it",
    "a named human at the vehicle who knows a test is running",
    "that human can reach the ignition key, the only e-stop",
    "nobody else near the vehicle",
]
DEFAULT_PULSE_MS = {"steer": 300, "brake": 300, "throttle": 1000}
ACTUATORS = {"steer", "steer_to", "brake", "throttle", "gear", "speed", "light", "ind", "horn", "clear"}


class Log:
    def __init__(self, path: str) -> None:
        self._f = open(path, "a", buffering=1)
        self._lock = threading.Lock()

    def event(self, kind: str, **fields) -> None:
        rec = {"ts": time.time(), "iso": datetime.now(timezone.utc).isoformat(), "kind": kind}
        rec.update(fields)
        with self._lock:
            self._f.write(json.dumps(rec, default=str) + "\n")


class Bench:
    def __init__(self, c: Ugv01Controls, log: Log) -> None:
        self.c = c
        self.log = log
        self.stop = threading.Event()

    # every prompt goes through here, so `safe` works everywhere
    def ask(self, prompt: str) -> str:
        while True:
            try:
                text = input(prompt).strip()
            except EOFError:
                return "quit"
            if text == "safe":
                self.safe("typed at prompt")
                continue
            return text

    def safe(self, why: str) -> None:
        self.log.event("safe_stop", why=why, before=self.c.snapshot())
        self.c.safe_stop()
        time.sleep(0.3)
        after = self.c.snapshot()
        self.log.event("safe_stop_done", after=after)
        print("STOP sent: duty zero, steering stop%s. requested=%s acked=%s" % (
            ", brake apply" if self.c._brake_on_stop else "",
            after["stop"]["requested"], after["stop"]["acked"]))

    def ticker(self) -> None:
        while not self.stop.is_set():
            self.c.heartbeat()      # the human is the watchdog on the bench
            self.c.tick()
            time.sleep(0.05)

    def run(self, line: str) -> None:
        parts = line.split()
        if not parts:
            return
        op, rest = parts[0], parts[1:]
        if op == "snap":
            print(json.dumps(self.c.snapshot(), indent=1, default=str)); return
        if op == "note":
            self.log.event("note", text=" ".join(rest)); return
        if op == "safe":
            self.safe("command"); return
        if op not in ACTUATORS:
            print("unknown: %s" % op); return
        try:
            plan = self._plan(op, rest)
        except (ValueError, IndexError) as e:
            print("bad command: %s" % e); return
        before = self.c.snapshot()
        print("About to: %s" % plan["say"])
        self.log.event("intent", command=line, plan=plan["say"], before=before)
        if self.ask("Type go: ") != "go":
            print("not sent"); self.log.event("declined", command=line); return
        err = None
        try:
            plan["do"]()
        except (Refused, ValueError) as e:
            err = str(e)
            print("REFUSED: %s" % err)
        self.log.event("sent", command=line, refused=err)
        if err is None and plan.get("after"):
            time.sleep(plan["ms"] / 1000.0)
            plan["after"]()
            self.log.event("pulse_ended", command=line, ms=plan["ms"])
        time.sleep(0.3)
        after = self.c.snapshot()
        print("steer %s deg  brake %s deg  duty acked %s  faults %s" % (
            after["steer"]["angle_deg"], after["brake"]["angle_deg"],
            after["accel"]["duty_acked"], after["faults"]))
        words = self.ask("What happened? > ")
        self.log.event("observed", command=line, refused=err, after=after, human=words)

    def _plan(self, op: str, rest: list[str]) -> dict:
        c = self.c
        def ms_of(i: int, kind: str) -> int:
            ms = int(rest[i]) if len(rest) > i else DEFAULT_PULSE_MS[kind]
            if not 50 <= ms <= 5000:
                raise ValueError("pulse must be 50 to 5000 ms")
            return ms
        if op == "steer":
            d = rest[0]
            if d == "stop":
                return {"say": "steering stop now", "do": lambda: c.steer("stop")}
            ms = ms_of(1, "steer")
            return {"say": "steer %s for %d ms, then stop" % (d, ms), "ms": ms,
                    "do": lambda: c.steer(d), "after": lambda: c.steer("stop")}
        if op == "brake":
            a = rest[0]
            if a == "stop":
                return {"say": "brake actuator stop now", "do": lambda: c.brake("stop")}
            ms = ms_of(1, "brake")
            return {"say": "brake %s for %d ms, then actuator stop" % (a, ms), "ms": ms,
                    "do": lambda: c.brake(a), "after": lambda: c.brake("stop")}
        if op == "throttle":
            pct = int(rest[0])
            if not 0 <= pct <= 100:
                raise ValueError("throttle is 0 to 100")
            cap = min(pct, c._max_duty)
            if pct == 0:
                return {"say": "throttle zero now", "do": lambda: c.set_throttle(0)}
            ms = ms_of(1, "throttle")
            return {"say": "throttle %d%% (capped to %d%%) for %d ms, then zero" % (pct, cap, ms),
                    "ms": ms, "do": lambda: c.set_throttle(pct), "after": lambda: c.set_throttle(0)}
        if op == "steer_to":
            deg = float(rest[0])
            if not math.isfinite(deg):
                raise ValueError("angle must be a number")
            return {"say": "closed-loop steer to %.1f deg; it keeps moving until there, or `safe`" % deg,
                    "do": lambda: c.steer_to(deg)}
        if op == "gear":
            return {"say": "gear %s" % rest[0], "do": lambda: c.gear(rest[0])}
        if op == "speed":
            return {"say": "speed mode %s" % rest[0], "do": lambda: c.speed_mode(int(rest[0]))}
        if op == "light":
            return {"say": "light %s" % rest[0], "do": lambda: c.light(rest[0])}
        if op == "ind":
            return {"say": "indicator %s" % rest[0], "do": lambda: c.indicator(rest[0])}
        if op == "horn":
            return {"say": "horn, one 0.5 s pulse", "do": c.horn}
        if op == "clear":
            return {"say": "clear latched faults; the next throttle needs a fresh zero ack", "do": c.clear_faults}
        raise ValueError(op)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ugv01 bench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", required=True, help="steering and brake controller port (CH340)")
    ap.add_argument("--accel", required=True, help="throttle board port (FTDI)")
    ap.add_argument("--steer-sense", choices=["right_increases", "left_increases"], default=None)
    ap.add_argument("--max-duty", type=int, default=30, help="bench cap on throttle duty (default 30)")
    ap.add_argument("--brake-on-stop", action="store_true",
                    help="include brake apply in the automatic stop (after the brake stroke has been seen)")
    ap.add_argument("--log", default="var/bench_ugv01_%s.jsonl" % datetime.now().strftime("%Y%m%d_%H%M"))
    args = ap.parse_args(argv)

    log = Log(args.log)
    print("ugv-01 bench. Log: %s" % args.log)
    print("Preconditions. Type each back, exactly, to continue.")
    for i, pre in enumerate(PRECONDITIONS, 1):
        typed = input("  %d. %s\n     > " % (i, pre)).strip()
        if typed != pre:
            print("Not confirmed. Nothing was opened."); log.event("abort", at="preconditions", typed=typed)
            return 1
    who = input("Name of the human at the key: ").strip()
    log.event("preconditions", confirmed=PRECONDITIONS, human=who, brake_on_stop=args.brake_on_stop,
              max_duty=args.max_duty)

    print("\nAbout to open %s and %s. Opening may reset both boards." % (args.drive, args.accel))
    print("Sent on open: INFO, STATUS, limits, angles to the drive board; duty ZERO then INFO to the throttle board.")
    print("Sent on a fault or on quit: duty zero and steering stop%s."
          % (", and brake apply" if args.brake_on_stop else " (no brake: --brake-on-stop not set)"))
    if input("Type go: ").strip() != "go":
        print("Not opened."); return 1

    c = Ugv01Controls(
        drive_port=PySerialPort(args.drive), accel_port=PySerialPort(args.accel),
        steer_sense=args.steer_sense, max_duty=args.max_duty, brake_on_stop=args.brake_on_stop,
        on_line=lambda name, line: log.event("rx", link=name, line=line),
        on_tx=lambda name, frame: log.event("tx", link=name, frame=frame.decode("ascii", "replace").strip()),
    )
    bench = Bench(c, log)

    def on_signal(signum, _frame):
        log.event("signal", signum=signum)
        bench.stop.set()
        try:
            c.close()
        finally:
            sys.exit(3)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, on_signal)

    try:
        try:
            c.start()
        except LinkError as e:
            print("start failed, ports closed: %s" % e); log.event("start_failed", error=str(e))
            return 2
        snap = c.snapshot()
        log.event("started", snapshot=snap)
        print(json.dumps(snap, indent=1, default=str))
        threading.Thread(target=bench.ticker, daemon=True, name="bench-tick").start()
        while True:
            line = bench.ask("bench> ")
            if line == "quit":
                break
            bench.run(line)
    except KeyboardInterrupt:
        log.event("interrupted")
    finally:
        bench.stop.set()
        print("stop, then close")
        c.close()
        log.event("closed", snapshot=c.snapshot())
    return 0


if __name__ == "__main__":
    sys.exit(main())
