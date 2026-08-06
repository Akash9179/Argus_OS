"""Puts the driven vehicle on the map.

Feeds the vehicle adapter's telemetry into TRACK over LINK, reusing the
reference client (sim.link_client) - the same five messages every asset
speaks. Position is dead-reckoned from speed and heading out of a
configured start point; the real vehicle replaces dead reckoning with real
positioning (ZED positional tracking or GNSS) without touching this seam.

Placement note: on the full vehicle PILOT owns LINK. This reporter exists
so a bench vehicle (the mock) or a survey-phase vehicle that is not yet
running PILOT still appears in the world. It is optional and off unless
the daemon is started with --report.

Manual-mode honesty: a vehicle under teleoperation does not execute tasks,
so incoming orders are logged and left unaccepted rather than silently
swallowed or falsely acknowledged.
"""
from __future__ import annotations

import logging
import math
import threading
import time

from link.v1.ontology_pb2 import (
    ASSET_STATUS_ACTIVE,
    ASSET_STATUS_STANDBY,
    Position,
)

from .vehicle import VehicleAdapter

log = logging.getLogger(__name__)

HEARTBEAT_EVERY_S = 2.0
TELEMETRY_EVERY_S = 0.5
EARTH_M_PER_DEG_LAT = 111_320.0


class LinkReporter:
    """Background thread: adapter telemetry -> LINK heartbeat + telemetry."""

    def __init__(
        self,
        vehicle: VehicleAdapter,
        asset_id: str,
        latitude_deg: float,
        longitude_deg: float,
        mqtt_host: str = "127.0.0.1",
        mqtt_port: int = 1883,
        topic_prefix: str = "argus",
    ) -> None:
        # Imported here so the bridge stays stdlib-only unless reporting is on.
        from sim.link_client import LinkClient
        from sim.transport import MqttVehicleLink

        self.vehicle = vehicle
        self.lat = latitude_deg
        self.lon = longitude_deg
        self._link = MqttVehicleLink(mqtt_host, mqtt_port, client_id=f"bridge-{asset_id}")
        self._client = LinkClient(asset_id, self._link, topic_prefix, on_task=self._refuse_task)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ api
    def start(self) -> None:
        self._link.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._link.stop()

    # ---------------------------------------------------------------- internals
    def _refuse_task(self, assignment) -> None:  # noqa: ANN001 - proto type
        log.warning(
            "task %s ignored: this vehicle is under manual control",
            getattr(assignment, "task_id", "?"),
        )

    def _position(self) -> Position:
        return Position(latitude_deg=self.lat, longitude_deg=self.lon)

    def dead_reckon(self, speed_mps: float, heading_deg: float, dt: float) -> None:
        """Advance the estimated position. Heading 0 is north, clockwise."""
        if speed_mps <= 0 or dt <= 0:
            return
        d = speed_mps * dt
        rad = math.radians(heading_deg)
        self.lat += (d * math.cos(rad)) / EARTH_M_PER_DEG_LAT
        m_per_deg_lon = EARTH_M_PER_DEG_LAT * math.cos(math.radians(self.lat))
        if m_per_deg_lon > 1.0:
            self.lon += (d * math.sin(rad)) / m_per_deg_lon

    def step(self, dt: float, send_heartbeat: bool) -> None:
        """One reporting step; separated from the thread loop for tests."""
        tel = self.vehicle.read()
        speed_mps = tel.speedKmh / 3.6
        self.dead_reckon(speed_mps, tel.headingDeg, dt)
        self._client.telemetry(self._position(), tel.headingDeg, speed_mps)
        if send_heartbeat:
            status = ASSET_STATUS_ACTIVE if tel.safetyState == "DRIVING" else ASSET_STATUS_STANDBY
            self._client.heartbeat(
                asset_class="ugv",
                status=status,
                battery_fraction=float(tel.battery["percent"]) / 100.0,
                position=self._position(),
                current_task_id="",
            )

    def _run(self) -> None:
        last = time.monotonic()
        next_heartbeat = 0.0
        while not self._stop.is_set():
            time.sleep(TELEMETRY_EVERY_S)
            now = time.monotonic()
            dt, last = now - last, now
            send_hb = now >= next_heartbeat
            if send_hb:
                next_heartbeat = now + HEARTBEAT_EVERY_S
            try:
                self.step(dt, send_hb)
            except Exception:  # keep reporting through transient broker faults
                log.exception("link report failed; continuing")
