#!/usr/bin/env python3
"""Listen on ugv-01's two boards and timestamp every line they print.

Purpose (15 Oct 2026): decide whether the drive module resets when the
jeep's ignition is switched on. The team reports lights, indicators and
horn flickering together at ignition. If the ESP32 resets, it prints its
boot banner (``0x00;OK;<version>``) and this script flags it. If no line
appears while the relays flicker, the board kept running and the relay
module's own power-up is the cause (pull-ups on the relay inputs).

This script sends nothing. It only reads. It still opens both serial
ports, and opening a port resets the board on the other end (DTR), so it
is gated like every other bench tool: human at the key, wheels up, typed
go. It asks pyserial to hold DTR and RTS low before opening, which avoids
the reset on some adapters and not on others; either way the boot banner
printed at open is reported as "open", not as an ignition reset.

Usage, from ~/argus on the Jetson:
  python3 bodies/ugv-01/bench-logs/2026-10-15/ignition_monitor.py \
      --drive /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
      --accel /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A5069RR4-if00-port0 \
      --log var/ignition_2026-10-15.jsonl
Then the human turns the key while this runs. Ctrl-C to stop.
"""
import argparse
import json
import sys
import threading
import time

import serial

BANNER = "0x00;OK;"


def open_quiet(path: str) -> serial.Serial:
    s = serial.Serial()
    s.port = path
    s.baudrate = 115200
    s.timeout = 0.2
    s.dtr = False
    s.rts = False
    s.open()
    return s


def listen(name: str, port: serial.Serial, log, lock, t_open: float) -> None:
    buf = b""
    while True:
        try:
            chunk = port.read(256)
        except serial.SerialException as e:
            with lock:
                rec = {"t": time.time(), "board": name, "event": "port_error", "error": str(e)}
                log.write(json.dumps(rec) + "\n"); log.flush()
                print(f"{name}: port error {e}", flush=True)
            return
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("ascii", "replace").strip("\r")
            now = time.time()
            event = "line"
            if line.startswith(BANNER):
                event = "boot_at_open" if now - t_open < 3.0 else "RESET"
            rec = {"t": now, "board": name, "event": event, "line": line}
            with lock:
                log.write(json.dumps(rec) + "\n"); log.flush()
                mark = "  <-- BOARD RESET" if event == "RESET" else ""
                print(f"{time.strftime('%H:%M:%S', time.localtime(now))}.{int(now % 1 * 1000):03d} {name}: {line}{mark}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive", required=True, help="drive module port (ESP32-S3)")
    ap.add_argument("--accel", required=True, help="throttle board port (Nano)")
    ap.add_argument("--log", required=True, help="jsonl file to append to")
    a = ap.parse_args()

    print("ignition monitor. Opening %s and %s may reset both boards." % (a.drive, a.accel))
    print("Preconditions: drive wheels on jacks, a human at the key, nothing else holding the ports.")
    who = input("Name of the human at the key: ").strip()
    if input("Type go: ").strip() != "go":
        print("Not opened.")
        return 1

    lock = threading.Lock()
    with open(a.log, "a") as log:
        log.write(json.dumps({"t": time.time(), "event": "go", "human": who}) + "\n"); log.flush()
        ports = {}
        for name, path in (("drive", a.drive), ("accel", a.accel)):
            try:
                ports[name] = open_quiet(path)
            except serial.SerialException as e:
                print(f"cannot open {name} at {path}: {e}", file=sys.stderr)
                return 2
        t_open = time.time()
        log.write(json.dumps({"t": t_open, "event": "opened", "drive": a.drive, "accel": a.accel}) + "\n"); log.flush()
        print("listening on both boards, sending nothing. Turn the key when ready. Ctrl-C to stop.", flush=True)
        threads = [threading.Thread(target=listen, args=(n, p, log, lock, t_open), daemon=True) for n, p in ports.items()]
        for t in threads:
            t.start()
        try:
            while any(t.is_alive() for t in threads):
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            for p in ports.values():
                try:
                    p.close()
                except Exception:
                    pass
            log.write(json.dumps({"t": time.time(), "event": "closed"}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
