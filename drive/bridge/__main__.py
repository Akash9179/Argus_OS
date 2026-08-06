"""Run the bridge daemon.

    ARGUS_PASSWORD=secret python3 -m drive.bridge                 # mock vehicle, :8090
    ARGUS_PASSWORD=secret python3 -m drive.bridge --port 9000 --watchdog-ms 700

The real ugv-01 adapter is selected with --vehicle once it exists (after the
hardware survey). Until then, mock is the only choice and the default.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys

from .daemon import BridgeDaemon
from .vehicle import MockVehicle


def main() -> int:
    ap = argparse.ArgumentParser(prog="drive.bridge", description="ARGUS DRIVE vehicle daemon")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--vehicle", choices=["mock"], default="mock")
    ap.add_argument("--watchdog-ms", type=int, default=700)
    ap.add_argument("--report", action="store_true",
                    help="announce this vehicle to TRACK over LINK (needs the OS venv, not stdlib-only)")
    ap.add_argument("--asset-id", default="01BENCHUGV0000000000000001")
    ap.add_argument("--latitude", type=float, default=51.5055)
    ap.add_argument("--longitude", type=float, default=-0.118)
    ap.add_argument("--mqtt-host", default="127.0.0.1")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    args = ap.parse_args()

    password = os.environ.get("ARGUS_PASSWORD", "")
    if not password:
        print("refusing to start: set ARGUS_PASSWORD", file=sys.stderr)
        return 2

    vehicle = MockVehicle()
    daemon = BridgeDaemon(
        vehicle, password, host=args.host, port=args.port,
        watchdog_timeout_s=args.watchdog_ms / 1000.0,
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
          f"watchdog={args.watchdog_ms}ms report={'on' if reporter else 'off'}")

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
