"""The service interfaces: the surface C2 and every future application uses."""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest
from link.v1.ontology_pb2 import Asset, AssetStatus, Entity, Position, Track

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


async def test_assets_carry_a_display_name_resolved_by_the_server(client, world):
    """C2 must never have to invent a name for a machine.

    Naming lives in the server's language file. An application that composed
    a name out of asset_class would be reaching below the hardware
    abstraction layer, and would become a second naming authority.
    """
    named = Asset(asset_id="01NAMED0000000000000000001", asset_class="ugv")
    named.capabilities.update({"name": "Gatekeeper"})
    world.store.put_asset(named)
    world.store.put_asset(Asset(asset_id="01UNNAMED000000000000000A1", asset_class="ugv"))

    by_id = {a["asset_id"]: a for a in (await client.get("/v1/assets")).json()}

    assert by_id["01NAMED0000000000000000001"]["display_name"] == "Gatekeeper"

    fallback = by_id["01UNNAMED000000000000000A1"]["display_name"]
    assert fallback, "an unnamed machine still needs something to call it"
    assert "01UNNAMED" not in fallback, "operators never read identifiers"
    assert "ugv" not in fallback.lower(), "the class code is not operator language"


async def test_an_order_names_the_person_not_their_identifier(client, world):
    """Operators read names. An identifier on screen is a waterline leak."""
    world.store.put_asset(Asset(asset_id="01ORDERTARGET00000000000A1", asset_class="ugv"))
    await client.post(
        "/v1/tasks",
        json={
            "asset_id": "01ORDERTARGET00000000000A1",
            "task_type": "navigate",
            "waypoints": [{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}],
        },
    )
    sources = [e["source"] for e in (await client.get("/v1/events")).json()]
    ordered = [s for s in sources if s.startswith("Ordered by")]
    assert ordered, "issuing an order should say who ordered it"
    for source in ordered:
        assert "operator-1" not in source, "that is an identifier, not a name"
        assert "Operator" in source


async def test_contacts_carry_a_name_resolved_by_the_server(client, world):
    """A contact's name, hedge included, is the server's to decide.

    "Possible person" rather than "person" is the honesty law showing up in
    a two-word label. An application that assembled this out of an entity
    class and a confidence number would be free to drop the hedge, and the
    hedge is the part that matters.
    """
    entity = Entity(entity_id="01ENTITYPERSON0000000000A1", entity_class="person")
    world.store.put_entity(entity)
    unsure = Track(
        track_id="01TRACKUNSURE00000000000A1",
        entity_id=entity.entity_id,
        confidence=0.42,
        position=Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON),
    )
    sure = Track(
        track_id="01TRACKSURE0000000000000A1",
        entity_id=entity.entity_id,
        confidence=0.91,
        position=Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON),
    )
    world.store.put_track(unsure)
    world.store.put_track(sure)

    by_id = {t["track_id"]: t for t in (await client.get("/v1/tracks")).json()}

    assert by_id["01TRACKUNSURE00000000000A1"]["display_name"] == "Possible person"
    assert by_id["01TRACKSURE0000000000000A1"]["display_name"] == "Person"
    for view in by_id.values():
        assert "01ENTITY" not in view["display_name"], "operators never read identifiers"


async def test_a_contact_says_where_it_is_only_when_we_know(client, world, gate_zone):
    """Somewhere vague is worse than nowhere, so an unknown place says nothing."""
    entity = Entity(entity_id="01ENTITYPLACED0000000000A1", entity_class="person")
    world.store.put_entity(entity)
    inside = Track(
        track_id="01TRACKINSIDE00000000000A1",
        entity_id=entity.entity_id,
        confidence=0.42,
        position=Position(latitude_deg=SITE_LAT + 0.0003, longitude_deg=SITE_LON),
    )
    outside = Track(
        track_id="01TRACKOUTSIDE0000000000A1",
        entity_id=entity.entity_id,
        confidence=0.42,
        position=Position(latitude_deg=SITE_LAT - 0.05, longitude_deg=SITE_LON - 0.05),
    )
    world.store.put_track(inside)
    world.store.put_track(outside)

    by_id = {t["track_id"]: t for t in (await client.get("/v1/tracks")).json()}

    assert by_id["01TRACKINSIDE00000000000A1"]["place"] == f"Inside {gate_zone.name}"
    assert by_id["01TRACKOUTSIDE0000000000A1"]["place"] == ""


async def test_a_contact_with_no_entity_still_has_something_to_call_it(client, world):
    """A track whose entity has gone is not a reason to show a blank label."""
    world.store.put_track(
        Track(
            track_id="01TRACKORPHANED000000000A1",
            confidence=0.42,
            position=Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON),
        )
    )
    view = (await client.get("/v1/tracks/01TRACKORPHANED000000000A1")).json()
    assert view["display_name"].strip(), "a contact always needs something to call it"
    assert "01TRACK" not in view["display_name"]


async def test_who_is_signed_in_is_a_name_never_an_identifier(client):
    """The menu bar shows a person. `principal_id` stays below the waterline."""
    me = (await client.get("/v1/me")).json()
    assert me["display_name"] == "Test Operator"
    assert "operator-1" not in me["display_name"]


async def test_an_order_carries_the_name_of_whoever_gave_it(client, world):
    """An application that wants to say who ordered something needs a name.

    Without one it would have to read `issued_by.principal_id`, and the only
    thing it could put on screen is an identifier.
    """
    world.store.put_asset(Asset(asset_id="01ORDERNAMED000000000000A1", asset_class="ugv"))
    issued = (
        await client.post(
            "/v1/tasks",
            json={
                "asset_id": "01ORDERNAMED000000000000A1",
                "task_type": "navigate",
                "waypoints": [{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}],
            },
        )
    ).json()
    assert issued["ordered_by"] == "Test Operator"
    assert "operator-1" not in issued["ordered_by"]


async def test_an_order_a_station_gave_itself_is_not_credited_to_the_operator(client, world):
    """Automatic tasking must not read as an order the operator gave.

    C2 issues its own standing-order tasks on the operator's token, so the
    person is genuinely the signed-in operator. The channel is the part that
    says they did not click anything, and the feed has to carry it.
    """
    world.store.put_asset(Asset(asset_id="01ORDERAUTO0000000000000A1", asset_class="ugv"))
    await client.post(
        "/v1/tasks",
        json={
            "asset_id": "01ORDERAUTO0000000000000A1",
            "task_type": "navigate",
            "waypoints": [{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}],
            "channel": "automatic",
        },
    )
    sources = [e["source"] for e in (await client.get("/v1/events")).json()]
    ordered = [s for s in sources if s.startswith("Ordered")]
    assert ordered, "issuing an order should say how it was ordered"
    assert any("without being asked" in s for s in ordered), (
        "an order nobody clicked must say so, or the feed credits the operator with it"
    )
    assert not any("Test Operator" in s for s in ordered), (
        "naming a person here would contradict the reason on the order itself"
    )


async def test_an_order_with_no_issuer_on_record_names_nobody(client, world):
    """A task the platform created itself must not grow a person.

    Falling back to "someone signed in" would assert a human the record does
    not have, and would disagree with the event feed, which calls the same
    order the system's.
    """
    from link.v1.ontology_pb2 import Task as TaskProto

    world.store.put_asset(Asset(asset_id="01ORDERNOBODY00000000000A1", asset_class="ugv"))
    world.store.put_task(
        TaskProto(
            task_id="01TASKNOISSUER000000000A1",
            asset_id="01ORDERNOBODY00000000000A1",
            task_type="navigate",
        )
    )
    view = (await client.get("/v1/tasks/01TASKNOISSUER000000000A1")).json()
    assert view["ordered_by"] == "", "no issuer on record means no person to name"
    assert "signed in" not in view["reason"]


async def test_a_self_issued_order_never_reads_as_a_persons_order(client, world):
    """The reason travels with the order, so no application has to guess."""
    world.store.put_asset(Asset(asset_id="01ORDERREASON00000000000A1", asset_class="ugv"))
    body = {
        "asset_id": "01ORDERREASON00000000000A1",
        "task_type": "navigate",
        "waypoints": [{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}],
    }
    clicked = (await client.post("/v1/tasks", json={**body, "channel": "map"})).json()
    assert "Test Operator" in clicked["reason"]
    assert clicked["reason"].startswith("because")

    world.store.put_asset(Asset(asset_id="01ORDERREASON00000000000A2", asset_class="ugv"))
    itself = (
        await client.post(
            "/v1/tasks",
            json={**body, "asset_id": "01ORDERREASON00000000000A2", "channel": "automatic"},
        )
    ).json()
    assert "without anyone being asked" in itself["reason"]
    assert "Test Operator" not in itself["reason"], (
        "an order nobody clicked must not be attributed to the operator"
    )
    # The reason and the name have to agree. C2 does not render ordered_by
    # today, but this is the published interface: the next application to
    # show who ordered something would otherwise reproduce the very
    # misattribution the reason phrase was written to prevent.
    assert itself["ordered_by"] == "", (
        "a self-issued order names nobody on every surface, not just in its reason"
    )


async def test_a_channel_this_build_never_heard_of_still_reaches_the_operator(client, world):
    """An unfamiliar channel is read out, but never as its own token.

    Dropping it leaves the operator reading a bare name with no idea how the
    order arrived. Printing it raw puts a caller's identifier on an
    operator's screen. Saying it came from another system does neither.
    """
    world.store.put_asset(Asset(asset_id="01ORDERNEWCHAN00000000A1", asset_class="ugv"))
    await client.post(
        "/v1/tasks",
        json={
            "asset_id": "01ORDERNEWCHAN00000000A1",
            "task_type": "navigate",
            "waypoints": [{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}],
            "channel": "handheld_radio",
        },
    )
    sources = [e["source"] for e in (await client.get("/v1/events")).json()]
    ordered = [s for s in sources if s.startswith("Ordered")]
    assert any("cannot name" in s for s in ordered), (
        "an unfamiliar channel must say the route is unknown, not assert one"
    )
    assert not any("handheld_radio" in s for s in ordered), (
        "the raw token is system vocabulary and does not belong on an operator's screen"
    )
    assert not any("by another system" in s for s in ordered), (
        "claiming another system would report an operator's own click back as somebody else's"
    )


async def test_an_order_from_another_day_carries_its_date(world):
    """A bare clock time reads as today, which is wrong across midnight."""
    from datetime import date

    lang = world.language
    yesterday = datetime(2026, 8, 2, 23, 58)
    today = date(2026, 8, 3)
    assert lang.time_of_day(yesterday, today=today) != lang.time_of_day(yesterday)
    assert "August" in lang.time_of_day(yesterday, today=today)
    assert lang.time_of_day(datetime(2026, 8, 3, 9, 5), today=today) == "09:05 Z"


async def test_an_issuer_with_no_person_reads_the_same_on_both_surfaces(client, world):
    """The feed and the order itself must agree on whether a person acted.

    Not reachable through the task endpoint today, which always records a
    principal. It becomes reachable the moment anything else writes an
    Issuer, and the two surfaces disagreeing about who acted is exactly the
    failure this guard exists to prevent.
    """
    from link.v1.ontology_pb2 import Issuer, Task as TaskProto

    task = TaskProto(
        task_id="01TASKEMPTYISSUER0000A1",
        asset_id="01ORDEREMPTY000000000000A1",
        task_type="navigate",
        issued_by=Issuer(principal_id="", channel="map"),
    )
    world.store.put_asset(Asset(asset_id="01ORDEREMPTY000000000000A1", asset_class="ugv"))
    world.store.put_task(task)

    view = (await client.get("/v1/tasks/01TASKEMPTYISSUER0000A1")).json()
    assert view["ordered_by"] == ""
    assert view["reason"] == "", "no person on record means no reason to state"

    event = world.events.task_event("task_issued", task, None)
    assert "signed in" not in event.source, (
        "the feed must not invent a person the order does not name"
    )
