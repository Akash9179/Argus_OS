"""Run the bridge daemon.

    python3 -m drive.bridge                          # mock vehicle, :8090
    python3 -m drive.bridge --port 9000 --watchdog-ms 700

Operators authenticate with per-operator tokens from the operators file
(default var/bridge_operators.json, created with one starter operator on
first run; add a line per person). The old ARGUS_PASSWORD shared secret
is gone (ADR-0009): a shared password could never say who was driving.

Every session is logged to var/bridge_sessions.jsonl (--log to move it).

The real ugv-01 adapter is selected with --vehicle once it exists (after the
hardware survey). Until then, mock is the only choice and the default.
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
    ap.add_argument("--vehicle", choices=["mock"], default="mock")
    ap.add_argument("--watchdog-ms", type=int, default=700)
    ap.add_argument("--operators", default=os.environ.get(
        "ARGUS_OPERATORS", "var/bridge_operators.json"),
        help="per-operator token file (created with a starter entry if missing)")
    ap.add_argument("--log", default="var/bridge_sessions.jsonl",
                    help="session log, one JSON line per event")
    ap.add_argument("--report", action="store_true",
                    help="announce this vehicle to TRACK over LINK (needs the OS venv, not stdlib-only)")
    ap.add_argument("--asset-id", default="01BENCHUGV0000000000000001")
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
    vehicle = MockVehicle()
    daemon = BridgeDaemon(
        vehicle, operators, host=args.host, port=args.port,
        watchdog_timeout_s=args.watchdog_ms / 1000.0, log_path=args.log,
    )
    daemon.start()
    reporter = None
    if args.report:
        from .link_reporter import LinkReporter

        reporter = LinkReporter(
            vehicle, args.asset_id, args.latitude, args.longitude,
            mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port,
        )
        reporter.start()
    print(f"bridge up on ws://{args.host}:{args.port} vehicle={args.vehicle} "
          f"watchdog={args.watchdog_ms}ms report={'on' if reporter else 'off'} "
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
    print("bridge stopped; vehicle safe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
