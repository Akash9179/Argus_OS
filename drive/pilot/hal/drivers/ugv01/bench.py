"""ugv-01 bench: one command at a time, a human at the key, every word kept.

    .venv/bin/python -m pilot.hal.drivers.ugv01.bench \\
        --drive /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \\
        --accel /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A5069RR4-if00-port0

Rule zero applies. This tool refuses to open a port until the operator has
typed the five preconditions back. Opening a port may reset a board. Every
actuator command is shown first, sent only after "go", and followed by a
prompt for what the human saw; all of it goes to the log as JSON lines,
with every raw line either board said.

The host heartbeat is fed by this tool's own tick thread, so a slow typist
does not trigger a safe stop that moves the brake. The human at the
ignition key is the watchdog on the bench. `safe` is always one word away.

Commands:
  snap                      print the controls snapshot
  steer left|right|stop     momentary steering move
  steer_to <deg>            closed loop (needs --steer-sense)
  brake apply|release|stop  brake actuator
  throttle <0-100>          accelerator duty (refused until brake released)
  gear D|N|R                needs duty zero acknowledged
  speed 1|2|3   light off|ring|high|low   ind off|left|right|park   horn
  safe                      safe stop: duty zero, brake apply, steer stop
  clear                     clear latched faults (a human decision)
  note <text>               a line for the log
  quit                      safe stop, close, exit
"""
from __future__ import annotations

import argparse
import json
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

ACTUATORS = {"steer", "steer_to", "brake", "throttle", "gear", "speed", "light", "ind", "horn", "safe", "clear"}


class Log:
    def __init__(self, path: str) -> None:
        self._f = open(path, "a", buffering=1)
        self._lock = threading.Lock()

    def event(self, kind: str, **fields) -> None:
        rec = {"ts": time.time(), "iso": datetime.now(timezone.utc).isoformat(), "kind": kind}
        rec.update(fields)
        with self._lock:
            self._f.write(json.dumps(rec, default=str) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ugv01 bench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", required=True, help="ARGUS DRIVE module port (CH340)")
    ap.add_argument("--accel", required=True, help="accelerator board port (FTDI)")
    ap.add_argument("--steer-sense", choices=["right_increases", "left_increases"], default=None)
    ap.add_argument("--max-duty", type=int, default=30, help="bench cap on throttle duty (default 30)")
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
    log.event("preconditions", confirmed=PRECONDITIONS, human=who)

    print("\nAbout to open %s and %s. Opening may reset both boards." % (args.drive, args.accel))
    print("No actuator frame is sent on open: INFO, STATUS, limits, angles, then duty zero.")
    if input("Type go: ").strip() != "go":
        print("Not opened."); return 1

    c = Ugv01Controls(
        drive_port=PySerialPort(args.drive), accel_port=PySerialPort(args.accel),
        steer_sense=args.steer_sense, max_duty=args.max_duty,
        on_line=lambda name, line: log.event("rx", link=name, line=line),
    )
    try:
        c.start()
    except LinkError as e:
        print("start failed: %s" % e); log.event("start_failed", error=str(e))
        return 2
    snap = c.snapshot()
    log.event("started", snapshot=snap)
    print(json.dumps(snap, indent=1, default=str))

    stop = threading.Event()

    def ticker():
        while not stop.is_set():
            c.heartbeat()      # the human is the watchdog on the bench
            c.tick()
            time.sleep(0.05)
    threading.Thread(target=ticker, daemon=True, name="bench-tick").start()

    def run(line: str) -> None:
        parts = line.split()
        if not parts:
            return
        op, rest = parts[0], parts[1:]
        if op == "snap":
            print(json.dumps(c.snapshot(), indent=1, default=str)); return
        if op == "note":
            log.event("note", text=" ".join(rest)); return
        if op not in ACTUATORS:
            print("unknown: %s" % op); return
        before = c.snapshot()
        print("About to: %s %s" % (op, " ".join(rest)))
        if input("Type go: ").strip() != "go":
            print("not sent"); log.event("declined", command=line); return
        err = None
        try:
            if op == "steer": c.steer(rest[0])
            elif op == "steer_to": c.steer_to(float(rest[0]))
            elif op == "brake": c.brake(rest[0])
            elif op == "throttle": c.set_throttle(int(rest[0]))
            elif op == "gear": c.gear(rest[0])
            elif op == "speed": c.speed_mode(int(rest[0]))
            elif op == "light": c.light(rest[0])
            elif op == "ind": c.indicator(rest[0])
            elif op == "horn": c.horn()
            elif op == "safe": c.safe_stop()
            elif op == "clear": c.clear_faults()
        except (Refused, ValueError, IndexError) as e:
            err = str(e)
            print("REFUSED: %s" % err)
        time.sleep(0.5)
        after = c.snapshot()
        words = input("What happened? > ").strip()
        log.event("command", command=line, refused=err, before=before, after=after, human=words)
        print("steer %s deg  brake %s deg  duty acked %s  faults %s" % (
            after["steer"]["angle_deg"], after["brake"]["angle_deg"],
            after["accel"]["duty_acked"], after["faults"]))

    try:
        while True:
            try:
                line = input("bench> ").strip()
            except EOFError:
                break
            if line == "quit":
                break
            run(line)
    finally:
        stop.set()
        print("safe stop, then close")
        c.close()
        log.event("closed", snapshot=c.snapshot())
    return 0


if __name__ == "__main__":
    sys.exit(main())
