"""Shared test fixtures.

The whole stack runs in one process: a simulated vehicle, the transport,
the world model, and the service interfaces. No broker and no Redis are
needed, so the loop that guards every change runs in seconds.
"""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest
import yaml
from link.v1.ontology_pb2 import Polygon, Position, Zone, ZoneRule

from sim.link_client import LinkClient
from sim.scenario import load_language
from sim.transport import DirectVehicleLink
from sim.vehicle import ScriptedObservation, SimulatedVehicle, VehicleConfig
from track.app import create_app
from track.config import Settings
from track.identity import ROLE_ADMIN, ROLE_OPERATOR, Principal, TokenDirectory
from track.ids import new_id
from track.live import MemoryLiveBus
from track.store import Store
from track.transport import MemoryTransport

OPERATOR_TOKEN = "test-operator-token"
ADMIN_TOKEN = "test-admin-token"

SITE_LAT = 51.50450
SITE_LON = -0.12000


async def wait_until(predicate, timeout: float = 8.0, interval: float = 0.05):
    """Poll until a condition holds, or fail the test with what it saw."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        await asyncio.sleep(interval)
    raise AssertionError(f"condition never became true within {timeout}s (last value: {last!r})")


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Timings compressed so the loop runs fast, behaviour unchanged."""
    return Settings(
        db_path=str(tmp_path / "track.db"),
        tokens_path=str(tmp_path / "tokens.yaml"),
        heartbeat_timeout_s=1.0,
        watchdog_interval_s=0.1,
        track_lost_after_s=1.5,
        track_close_after_s=30.0,
        task_ack_timeout_s=3.0,
        topic_prefix="testsite",
    )


@pytest.fixture
def store(settings) -> Store:
    s = Store(settings.db_path)
    yield s
    s.close()


@pytest.fixture
def transport() -> MemoryTransport:
    return MemoryTransport()


@pytest.fixture
def bus() -> MemoryLiveBus:
    return MemoryLiveBus()


@pytest.fixture
def tokens() -> TokenDirectory:
    return TokenDirectory(
        {
            OPERATOR_TOKEN: Principal("operator-1", "Test Operator", ROLE_OPERATOR),
            ADMIN_TOKEN: Principal("admin-1", "Test Administrator", ROLE_ADMIN),
        }
    )


@pytest.fixture
async def app(settings, store, transport, bus, tokens):
    """The server, running its full startup and shutdown."""
    application = create_app(
        settings=settings, transport=transport, store=store, bus=bus, tokens=tokens
    )
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    """An application talking to the server exactly as C2 will."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://server",
        headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"},
    ) as c:
        yield c


@pytest.fixture
def world(app):
    return app.state.world


class RunningVehicle:
    """A simulated vehicle running in its own thread, as a real one would."""

    def __init__(self, vehicle: SimulatedVehicle, link: DirectVehicleLink, client: LinkClient):
        self.vehicle = vehicle
        self.link = link
        self.client = client
        self._thread = threading.Thread(target=vehicle.run, daemon=True)

    def start(self) -> None:
        self.client.start()
        self._thread.start()

    def stop(self) -> None:
        """Stop the vehicle the way losing one looks from the server."""
        self.vehicle.stop()
        self.client.stop()
        self._thread.join(timeout=3.0)

    @property
    def asset_id(self) -> str:
        return self.vehicle.cfg.asset_id


@pytest.fixture
def make_vehicle(transport, settings):
    """Build a simulated vehicle wired straight to the server."""
    running: list[RunningVehicle] = []

    def _make(
        asset_id: str | None = None,
        asset_class: str = "ugv",
        speed_mps: float = 25.0,
        observations: list[ScriptedObservation] | None = None,
    ) -> RunningVehicle:
        config = VehicleConfig(
            asset_id=asset_id or new_id(),
            asset_class=asset_class,
            name="Test vehicle",
            start_latitude_deg=SITE_LAT,
            start_longitude_deg=SITE_LON,
            speed_mps=speed_mps,
            heartbeat_hz=5.0,
            telemetry_hz=10.0,
            observations=observations or [],
            messages=load_language(),
        )
        link = DirectVehicleLink(transport)
        holder: dict = {}
        client = LinkClient(
            asset_id=config.asset_id,
            link=link,
            topic_prefix=settings.topic_prefix,
            on_task=lambda assignment: holder["vehicle"].on_task(assignment),
        )
        vehicle = SimulatedVehicle(config, client)
        holder["vehicle"] = vehicle

        handle = RunningVehicle(vehicle, link, client)
        running.append(handle)
        return handle

    yield _make

    for handle in running:
        handle.stop()


class RunningMachine:
    """A booted edge runtime running in its own thread, as a real one does."""

    def __init__(self, runtime):
        self.runtime = runtime
        self._thread = threading.Thread(target=runtime.run, daemon=True)

    def start(self) -> None:
        self.runtime.start()
        self._thread.start()

    def stop(self) -> None:
        """Stop the machine the way losing one looks from the server."""
        self.runtime.stop()
        self._thread.join(timeout=3.0)

    @property
    def asset_id(self) -> str:
        return self.runtime.manifest.asset_id

    @property
    def comms(self):
        return self.runtime.drivers.comms

    @property
    def registry(self):
        return self.runtime.registry


@pytest.fixture
def make_machine(transport, settings, tmp_path):
    """Boot the edge runtime from a manifest, wired straight to the server.

    The manifest is written to a file first, because loading one from disk
    is what a machine actually does at boot and a test that skipped it
    would not be testing the thing that has to work.
    """
    from pilot.autonomy.core import RuntimeConfig
    from pilot.hal.drivers.simulated import DirectComms
    from pilot.hal.manifest import parse_manifest
    from pilot.runtime import boot, load_language

    running: list[RunningMachine] = []
    written = [0]

    def _make(manifest: dict, **overrides) -> RunningMachine:
        written[0] += 1
        path = tmp_path / f"manifest-{written[0]}.yaml"
        path.write_text(yaml.safe_dump(manifest))

        # Every machine gets its own store, as on real hardware, unless a
        # test hands two boots the same path to prove a reboot recovers.
        overrides.setdefault("state_path", tmp_path / f"state-{written[0]}.db")

        parsed = parse_manifest(manifest)
        comms = DirectComms(parsed, bus=transport)
        runtime = boot(
            path,
            topic_prefix=settings.topic_prefix,
            comms=comms,
            config=RuntimeConfig(
                messages=load_language(), heartbeat_hz=5.0, telemetry_hz=10.0, tick_s=0.01
            ),
            **overrides,
        )
        handle = RunningMachine(runtime)
        running.append(handle)
        return handle

    yield _make

    for handle in running:
        handle.stop()


def a_manifest(**changes) -> dict:
    """The reference machine, with anything a test wants to change.

    Speeds are unrealistically high so the loop runs in seconds; nothing
    else about the machine is altered.
    """
    manifest = {
        "asset_id": new_id(),
        "asset_class": "ugv",
        "name": "Test machine",
        "max_speed_mps": 25.0,
        "min_turn_radius_m": 0.0,
        "battery": {"start_fraction": 0.92, "drain_per_minute": 0.004},
        "drivers": [
            {
                "kind": "locomotion",
                "driver": "simulated_locomotion",
                "start_latitude_deg": SITE_LAT,
                "start_longitude_deg": SITE_LON,
            },
            {"kind": "comms", "driver": "direct_comms"},
        ],
    }
    manifest.update(changes)
    return manifest


def a_camera_seeing_a_person(**changes) -> dict:
    """A sensor driver entry whose scripted sighting is a weak detection."""
    sighting = {
        "after_seconds": 0.3,
        "entity_class": "person",
        "confidence": 0.45,
        "offset_north_m": 20,
        "offset_east_m": 6,
        "narration": "possible person near the fence line, low confidence",
        "repeat_every_seconds": 0.3,
        "count": 8,
    }
    sighting.update(changes)
    return {"kind": "sensor", "driver": "simulated_camera", "sightings": [sighting]}


@pytest.fixture
def gate_zone(store) -> Zone:
    """A protected zone that raises an alert when something enters it."""
    zone = Zone(
        zone_id=new_id(),
        name="Gate 3",
        zone_type="protected",
        geometry=Polygon(
            exterior=[
                Position(latitude_deg=SITE_LAT + 0.0001, longitude_deg=SITE_LON - 0.0004),
                Position(latitude_deg=SITE_LAT + 0.0006, longitude_deg=SITE_LON - 0.0004),
                Position(latitude_deg=SITE_LAT + 0.0006, longitude_deg=SITE_LON + 0.0006),
                Position(latitude_deg=SITE_LAT + 0.0001, longitude_deg=SITE_LON + 0.0006),
            ]
        ),
        rules=[ZoneRule(rule_type="alert_on_entry", parameters={"threat_level": "medium"})],
    )
    store.put_zone(zone)
    return zone
