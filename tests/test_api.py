"""The service interfaces: the surface C2 and every future application uses."""

from __future__ import annotations

import httpx
import pytest
from link.v1.ontology_pb2 import Asset, AssetStatus

from track.ids import new_id, now_ts

from tests.conftest import ADMIN_TOKEN, OPERATOR_TOKEN, SITE_LAT, SITE_LON


@pytest.fixture
def registered_asset(store) -> Asset:
    asset = Asset(
        asset_id=new_id(),
        asset_class="ugv",
        status=AssetStatus.ASSET_STATUS_ACTIVE,
        last_heartbeat=now_ts(),
    )
    asset.capabilities.update({"name": "UGV-1"})
    store.put_asset(asset)
    return asset


async def test_every_interface_requires_a_caller(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://server"
    ) as anonymous:
        for path in ("/v1/assets", "/v1/tracks", "/v1/events", "/v1/tasks", "/v1/zones"):
            assert (await anonymous.get(path)).status_code == 401


async def test_health_is_open_and_states_the_contract_version(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://server"
    ) as anonymous:
        body = (await anonymous.get("/health")).json()
    assert body["link_version"] == 1
    assert body["ontology_version"] == 1


async def test_operators_cannot_do_administration(client):
    response = await client.post(
        "/v1/zones",
        json={"name": "Gate 4", "zone_type": "protected", "geometry": [], "rules": []},
    )
    assert response.status_code == 403


async def test_an_administrator_can_create_a_zone(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://server",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    ) as admin:
        response = await admin.post(
            "/v1/zones",
            json={
                "name": "Gate 4",
                "zone_type": "protected",
                "geometry": [
                    {"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON},
                    {"latitude_deg": SITE_LAT + 0.001, "longitude_deg": SITE_LON},
                    {"latitude_deg": SITE_LAT + 0.001, "longitude_deg": SITE_LON + 0.001},
                ],
                "rules": [{"rule_type": "alert_on_entry", "parameters": {"threat_level": "low"}}],
            },
        )
    assert response.status_code == 201
    assert response.json()["name"] == "Gate 4"


async def test_ordering_a_machine_we_do_not_have_is_refused_in_plain_words(client):
    response = await client.post(
        "/v1/tasks", json={"asset_id": "nobody", "task_type": "navigate", "waypoints": []}
    )
    assert response.status_code == 409
    assert "not known" in response.json()["detail"]


async def test_an_order_records_who_gave_it_and_how(client, registered_asset):
    response = await client.post(
        "/v1/tasks",
        json={
            "asset_id": registered_asset.asset_id,
            "task_type": "navigate",
            "waypoints": [{"latitude_deg": SITE_LAT + 0.0005, "longitude_deg": SITE_LON}],
            "channel": "voice",
        },
    )
    assert response.status_code == 201
    task = response.json()
    assert task["issued_by"]["principal_id"] == "operator-1"
    assert task["issued_by"]["channel"] == "voice"
    assert task["status"] == "TASK_STATE_PENDING"


async def test_an_order_reaches_the_machine_over_the_contract(client, registered_asset, transport, settings):
    await client.post(
        "/v1/tasks",
        json={
            "asset_id": registered_asset.asset_id,
            "task_type": "navigate",
            "waypoints": [{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}],
        },
    )
    topics = [topic for topic, _ in transport.published]
    assert f"{settings.topic_prefix}/{registered_asset.asset_id}/task" in topics


async def test_an_order_type_this_build_never_heard_of_is_still_sent(client, registered_asset):
    """The server does not police the vocabulary. The machine decides."""
    response = await client.post(
        "/v1/tasks",
        json={"asset_id": registered_asset.asset_id, "task_type": "sweep_for_mines", "extras": {"width_m": 3}},
    )
    assert response.status_code == 201
    assert response.json()["task_type"] == "sweep_for_mines"


async def test_an_administrator_names_a_machine(app, registered_asset):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://server",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    ) as admin:
        response = await admin.put(
            f"/v1/assets/{registered_asset.asset_id}", json={"name": "Scout 2"}
        )
    assert response.json()["capabilities"]["name"] == "Scout 2"


# The live stream is tested synchronously, with its own application, so the
# test client runs startup and shutdown itself rather than nesting inside an
# already-running server.


def test_the_live_stream_refuses_a_caller_without_a_token(settings, store, transport, bus, tokens):
    from fastapi.testclient import TestClient

    from track.app import create_app

    app = create_app(settings=settings, transport=transport, store=store, bus=bus, tokens=tokens)
    with TestClient(app) as sync_client:
        with pytest.raises(Exception):
            with sync_client.websocket_connect("/v1/stream"):
                pass


def test_the_live_stream_opens_with_a_full_picture(
    settings, store, transport, bus, tokens, registered_asset
):
    from fastapi.testclient import TestClient

    from track.app import create_app

    app = create_app(settings=settings, transport=transport, store=store, bus=bus, tokens=tokens)
    with TestClient(app) as sync_client:
        with sync_client.websocket_connect(f"/v1/stream?token={OPERATOR_TOKEN}") as socket:
            first = socket.receive_json()

    assert first["kind"] == "snapshot"
    for section in ("assets", "tracks", "zones", "tasks", "events", "telemetry"):
        assert section in first["data"]
    assert first["data"]["assets"][0]["asset_id"] == registered_asset.asset_id
