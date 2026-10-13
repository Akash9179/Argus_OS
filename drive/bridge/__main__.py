"""Run the bridge daemon.

    python3 -m drive.bridge                          # mock vehicle, :8090
    python3 -m drive.bridge --port 9000 --watchdog-ms 700
    python3 -m drive.bridge --report --name Tessy    # on the vehicle: on the map, by name

--name is what TRACK shows for this machine (its manifest name, declared
once over LINK when --report is on). Without it TRACK falls back to a
readable label built from the asset class and id; nothing here guesses a
real vehicle's name.

Operators authenticate with per-operator tokens from the operators file
(default var/bridge_operators.json, created with one starter operator on
first run; add a line per person). The old ARGUS_PASSWORD shared secret
is gone (ADR-0009): a shared password could never say who was driving.

Every session is logged to var/bridge_sessions.jsonl (--log to move it).

--vehicle ugv01 selects the real adapter (drive/bridge/ugv01.py, a shim over
the HAL driver). Mock is the default. The real one cannot arm until the
section 6 gate is proven; it is for the bench and the inventory of state.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys

from .daemon import BridgeDaemon
from .identity import OperatorDirectory
from .vehicle import MockVehicle


def main() -> int:
    ap = argparse.ArgumentParser(prog="drive.bridge", description="ARGUS DRIVE vehicle daemon")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--vehicle", choices=["mock", "ugv01"], default="mock",
                    help="ugv01 opens two real serial ports. Rule zero: never on a "
                         "vehicle without wheels up and a human at the key.")
    ap.add_argument("--drive-port", default=None,
                    help="ugv01: the steering and brake controller's port, by-id path "
                         "(bodies/ugv-01/FINDINGS-2026-10-13.md); required with --vehicle ugv01")
    ap.add_argument("--accel-port", default=None,
                    help="ugv01: the throttle board's port, by-id path; required with --vehicle ugv01")
    ap.add_argument("--steer-sense", choices=["right_increases", "left_increases"],
                    default=None, help="ugv01: which way raises the angle reading; from the bench")
    ap.add_argument("--watchdog-ms", type=int, default=700)
    ap.add_argument("--operators", default=os.environ.get(
        "ARGUS_OPERATORS", "var/bridge_operators.json"),
        help="per-operator token file (created with a starter entry if missing)")
    ap.add_argument("--log", default="var/bridge_sessions.jsonl",
                    help="session log, one JSON line per event")
    ap.add_argument("--report", action="store_true",
                    help="announce this vehicle to TRACK over LINK (needs the OS venv, not stdlib-only)")
    ap.add_argument("--asset-id", default="01BENCHUGV0000000000000001")
    ap.add_argument("--name", default=None,
                    help="this vehicle's display name, declared to TRACK with --report "
                         "(no default: an unnamed machine gets TRACK's fallback label)")
    ap.add_argument("--latitude", type=float, default=51.5055)
    ap.add_argument("--longitude", type=float, default=-0.118)
    ap.add_argument("--mqtt-host", default="127.0.0.1")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    args = ap.parse_args()

    if os.environ.get("ARGUS_PASSWORD"):
        # Said out loud rather than silently ignored: someone following an
        # old runbook must find out here, not after a failed auth.
        print("note: ARGUS_PASSWORD is no longer used; operators authenticate "
              f"with their own token from {args.operators}", file=sys.stderr)

    operators = OperatorDirectory.from_file(args.operators)
    controls = None
    if args.vehicle == "ugv01":
        if not args.drive_port or not args.accel_port:
            ap.error("--vehicle ugv01 needs --drive-port and --accel-port (no defaults above the HAL)")
        # Rule zero (CLAUDE.md): opening these ports may reset the boards.
        # Nothing here moves on its own, but the human must have wheels
        # up and the key in hand before this line runs.
        from pilot.hal.drivers.ugv01.controls import Ugv01Controls
        from pilot.hal.drivers.ugv01.link import PySerialPort
        from .ugv01 import Ugv01Vehicle

        controls = Ugv01Controls(
            drive_port=PySerialPort(args.drive_port),
            accel_port=PySerialPort(args.accel_port),
            steer_sense=args.steer_sense,
        )
        print(f"ugv01: opening {args.drive_port} and {args.accel_port}; "
              "the accelerator board reboots on open", file=sys.stderr)
        controls.start()
        snap = controls.snapshot()
        print(f"ugv01: drive v{snap['drive']['firmware']} accel v{snap['accel']['firmware']} "
              f"steer {snap['steer']['angle_deg']} deg limits {snap['steer']['limits_deg']} "
              f"brake {snap['brake']['angle_deg']} deg", file=sys.stderr)
        vehicle = Ugv01Vehicle(controls)
    else:
        vehicle = MockVehicle()
    daemon = BridgeDaemon(
        vehicle, operators, host=args.host, port=args.port,
        watchdog_timeout_s=args.watchdog_ms / 1000.0, log_path=args.log,
        name=args.name,
    )
    daemon.start()
    reporter = None
    if args.report:
        from .link_reporter import LinkReporter

        reporter = LinkReporter(
            vehicle, args.asset_id, args.latitude, args.longitude,
            mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port, name=args.name,
        )
        reporter.start()
    print(f"bridge up on ws://{args.host}:{args.port} vehicle={args.vehicle} "
          f"watchdog={args.watchdog_ms}ms report={'on' if reporter else 'off'} "
          f"name={args.name or '(none)'} "
          f"operators={args.operators} log={args.log}")

    stop = signal.SIGTERM, signal.SIGINT
    done = {"flag": False}

    def _halt(*_):
        done["flag"] = True

    for s in stop:
        signal.signal(s, _halt)
    try:
        while not done["flag"]:
            signal.pause()
    except AttributeError:  # windows
        import time
        while not done["flag"]:
            time.sleep(0.5)
    if reporter:
        reporter.stop()
    daemon.stop()
    if controls is not None:
        controls.close()      # stop first, then let go of the ports
        st = controls.snapshot()["stop"]
        print("bridge stopped; stop requested=%s acknowledged=%s (acknowledged is not verified)"
              % (st["requested"], st["acked"]))
    else:
        print("bridge stopped; mock vehicle at rest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
