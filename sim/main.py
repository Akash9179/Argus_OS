"""Run a simulated vehicle against a running broker."""

from __future__ import annotations

import argparse
import logging
import os
import signal

from sim import scenario
from sim.link_client import LinkClient
from sim.transport import MqttVehicleLink
from sim.vehicle import SimulatedVehicle

# Must match the world model server's topic prefix. Both sides default to the
# same placeholder product name; a deployment sets TOPIC_PREFIX on both.
DEFAULT_TOPIC_PREFIX = "argus"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simulated vehicle.")
    parser.add_argument("--scenario", default=str(scenario.DEFAULT_SCENARIO))
    parser.add_argument("--asset-id", default=None, help="Override the scenario's identifier.")
    parser.add_argument("--latitude", type=float, default=None)
    parser.add_argument("--longitude", type=float, default=None)
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--prefix", default=os.getenv("TOPIC_PREFIX", DEFAULT_TOPIC_PREFIX))
    parser.add_argument("--duration", type=float, default=None, help="Stop after this many seconds.")
    args = parser.parse_args()

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)-7s %(message)s")

    config = scenario.load(args.scenario)
    if args.asset_id:
        config.asset_id = args.asset_id
    if args.latitude is not None:
        config.start_latitude_deg = args.latitude
    if args.longitude is not None:
        config.start_longitude_deg = args.longitude

    vehicle: SimulatedVehicle | None = None

    def on_task(assignment):
        if vehicle is not None:
            vehicle.on_task(assignment)

    link = MqttVehicleLink(args.host, args.port, client_id=f"sim-{config.asset_id}")
    client = LinkClient(
        asset_id=config.asset_id,
        link=link,
        topic_prefix=args.prefix,
        on_task=on_task,
    )
    vehicle = SimulatedVehicle(config, client)

    def shutdown(*_):
        vehicle.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    client.start()
    try:
        vehicle.run(duration_s=args.duration)
    finally:
        client.stop()


if __name__ == "__main__":
    main()
