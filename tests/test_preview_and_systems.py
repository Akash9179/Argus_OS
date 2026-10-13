"""What an operator reads before approving an order, and what a machine says
about its own systems. Both are derived from what the platform actually
holds and both refuse to invent a fact it does not."""

from __future__ import annotations

import re

import httpx
import pytest
from google.protobuf.timestamp_pb2 import Timestamp
from link.v1.ontology_pb2 import Asset, AssetStatus, Polygon, Position

from track import geo
from track.ids import new_id, now_ts

from tests.conftest import ADMIN_TOKEN, SITE_LAT, SITE_LON

# Words that belong to the system, never to the operator.
JARGON = re.compile(
    r"asset_id|task_type|heartbeat_|registry|driver|manifest|payload|null|None|_",
    re.IGNORECASE,
)


def _square(lat: float, lon: float, half: float = 0.001) -> Polygon:
    return Polygon(
        exterior=[
            Position(latitude_deg=lat - half, longitude_deg=lon - half),
            Position(latitude_deg=lat + half, longitude_deg=lon - half),
            Position(latitude_deg=lat + half, longitude_deg=lon + half),
            Position(latitude_deg=lat - half, longitude_deg=lon + half),
        ]
    )


def _p(lat: float, lon: float) -> Position:
    return Position(latitude_deg=lat, longitude_deg=lon)


# -- geometry ---------------------------------------------------------------


def test_a_leg_passing_straight_through_a_place_crosses_it():
    square = _square(SITE_LAT, SITE_LON)
    assert geo.segment_crosses_polygon(
        _p(SITE_LAT, SITE_LON - 0.01), _p(SITE_LAT, SITE_LON + 0.01), square
    )


def test_a_leg_ending_inside_a_place_crosses_it():
    square = _square(SITE_LAT, SITE_LON)
    assert geo.segment_crosses_polygon(_p(SITE_LAT + 0.01, SITE_LON), _p(SITE_LAT, SITE_LON), square)
    assert geo.segment_crosses_polygon(_p(SITE_LAT, SITE_LON), _p(SITE_LAT + 0.01, SITE_LON), square)


def test_a_leg_that_stays_clear_does_not_cross():
    square = _square(SITE_LAT, SITE_LON)
    assert not geo.segment_crosses_polygon(
        _p(SITE_LAT + 0.005, SITE_LON - 0.01), _p(SITE_LAT + 0.005, SITE_LON + 0.01), square
    )
    # Fewer than three vertices enclose nothing.
    assert not geo.segment_crosses_polygon(
        _p(SITE_LAT, SITE_LON - 0.01), _p(SITE_LAT, SITE_LON + 0.01), Polygon(exterior=[])
    )


def test_a_leg_that_only_touches_the_edge_counts_as_crossing():
    """Grazing a keep-out boundary is worth a look, not a free pass."""
    square = _square(SITE_LAT, SITE_LON)
    # Ends exactly on the western edge.
    assert geo.segment_crosses_polygon(
        _p(SITE_LAT, SITE_LON - 0.01), _p(SITE_LAT, SITE_LON - 0.001), square
    )
    # Runs along the northern edge.
    assert geo.segment_crosses_polygon(
        _p(SITE_LAT + 0.001, SITE_LON - 0.01), _p(SITE_LAT + 0.001, SITE_LON + 0.01), square
    )


def test_a_route_crosses_if_any_leg_does():
    square = _square(SITE_LAT, SITE_LON)
    clear = [_p(SITE_LAT + 0.01, SITE_LON - 0.01), _p(SITE_LAT + 0.01, SITE_LON)]
    assert not geo.path_crosses_polygon(clear, square)
    # A third leg straight south, through the middle.
    assert geo.path_crosses_polygon(clear + [_p(SITE_LAT - 0.01, SITE_LON)], square)
    assert not geo.path_crosses_polygon([], square)
    assert geo.path_crosses_polygon([_p(SITE_LAT, SITE_LON)], square)
    assert not geo.path_crosses_polygon([_p(SITE_LAT + 0.01, SITE_LON)], square)


# -- the proposal -----------------------------------------------------------


@pytest.fixture
def ready_asset(store) -> Asset:
    """A machine that has just spoken, knows where it is, and has said what
    it can do and how fast it goes."""
    asset = Asset(
        asset_id=new_id(),
        asset_class="ugv",
        status=AssetStatus.ASSET_STATUS_ACTIVE,
        last_heartbeat=now_ts(),
        battery_fraction=0.9,
        position=Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON),
    )
    asset.capabilities.update(
        {"name": "UGV-1", "max_speed_mps": 2.0, "supported_task_types": "navigate, patrol"}
    )
    store.put_asset(asset)
    return asset


def _stale() -> Timestamp:
    stamp = Timestamp()
    stamp.FromDatetime(now_ts().ToDatetime().replace(year=2020))
    return stamp


async def _preview(client, asset_id: str, task_type: str = "navigate", waypoints=None) -> dict:
    response = await client.post(
        "/v1/tasks/preview",
        json={
            "asset_id": asset_id,
            "task_type": task_type,
            "waypoints": waypoints
            if waypoints is not None
            else [{"latitude_deg": SITE_LAT + 0.001, "longitude_deg": SITE_LON}],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _by_id(preview: dict) -> dict:
    return {c["id"]: c for c in preview["checks"]}


async def test_a_ready_machine_passes_every_check_and_gets_an_arrival_time(client, ready_asset):
    preview = await _preview(client, ready_asset.asset_id)
    checks = _by_id(preview)

    assert [c["id"] for c in preview["checks"]] == [
        "answering", "battery", "mode", "supports", "keep_out"
    ]
    assert {c["state"] for c in preview["checks"]} == {"pass"}
    assert preview["can_send"] is True

    # The route starts where the machine is, then goes where it is told.
    assert preview["path"][0] == {"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}
    assert preview["path"][1:] == preview["waypoints"]
    assert 100 < preview["distance_m"] < 125
    assert preview["speed_mps_assumed"] == 2.0
    assert preview["eta_sec"] == round(preview["distance_m"] / 2.0)

    # Provenance: every check says where its fact came from.
    assert all(c["source"] for c in preview["checks"])
    assert "heartbeat" in checks["answering"]["source"]
    assert checks["answering"]["source"].endswith("Z")
    assert "Declared by the machine" in checks["supports"]["source"]
    assert "No zones" in checks["keep_out"]["source"]


async def test_a_proposal_issues_nothing(client, ready_asset, transport, settings):
    await _preview(client, ready_asset.asset_id)
    assert (await client.get("/v1/tasks")).json() == []
    assert f"{settings.topic_prefix}/{ready_asset.asset_id}/task" not in [
        topic for topic, _ in transport.published
    ]


async def test_a_silent_machine_fails_the_answering_check_and_says_when_it_was_heard(
    client, store
):
    quiet = Asset(asset_id=new_id(), asset_class="ugv", last_heartbeat=_stale())
    quiet.capabilities.update({"name": "Scout 9"})
    store.put_asset(quiet)

    preview = await _preview(client, quiet.asset_id)
    checks = _by_id(preview)

    assert checks["answering"]["state"] == "fail"
    assert "Scout 9 has not answered since" in checks["answering"]["text"]
    assert " Z on " in checks["answering"]["text"], "an old time carries its date"
    assert preview["can_send"] is False

    # Facts we do not hold are unknown, never guessed.
    assert checks["battery"]["state"] == "unknown"
    assert checks["supports"]["state"] == "unknown"
    assert "has not said which orders" in checks["supports"]["text"]
    assert preview["eta_sec"] is None
    assert preview["speed_mps_assumed"] is None
    # No position known, so the route is just the waypoints.
    assert preview["path"] == preview["waypoints"]


async def test_a_machine_never_heard_from_fails_plainly(client, store):
    unheard = Asset(asset_id=new_id(), asset_class="ugv")
    store.put_asset(unheard)
    checks = _by_id(await _preview(client, unheard.asset_id))
    assert checks["answering"]["state"] == "fail"
    assert "never answered" in checks["answering"]["text"]


async def test_a_low_battery_needs_the_operator_but_does_not_block(client, store, ready_asset):
    ready_asset.battery_fraction = 0.15
    store.put_asset(ready_asset)
    preview = await _preview(client, ready_asset.asset_id)
    battery = _by_id(preview)["battery"]
    assert battery["state"] == "needs_you"
    assert "15 percent" in battery["text"]
    assert preview["can_send"] is True


async def test_a_machine_in_automatic_needs_the_operator_to_take_it_back(client, ready_asset):
    manual = _by_id(await _preview(client, ready_asset.asset_id))["mode"]
    assert manual["state"] == "pass"
    assert "Manual" in manual["text"]

    await client.put(f"/v1/assets/{ready_asset.asset_id}/autonomy", json={"mode": "automatic"})
    automatic = _by_id(await _preview(client, ready_asset.asset_id))["mode"]
    assert automatic["state"] == "needs_you"
    assert "Automatic" in automatic["text"]
    assert "Switch it to Manual" in automatic["text"]


async def test_a_mode_this_build_cannot_read_is_unknown(client, store, ready_asset):
    store.set_autonomy(ready_asset.asset_id, "supervised", "someone")
    mode = _by_id(await _preview(client, ready_asset.asset_id))["mode"]
    assert mode["state"] == "unknown"
    assert "supervised" not in mode["text"], "an unrecognised token is not operator language"


async def test_an_order_the_machine_never_declared_fails_the_supports_check(client, ready_asset):
    preview = await _preview(client, ready_asset.asset_id, task_type="sweep_for_mines")
    supports = _by_id(preview)["supports"]
    assert supports["state"] == "fail"
    assert "UGV-1 has not said it can" in supports["text"]
    assert "sweep_for_mines" not in supports["text"]
    assert preview["can_send"] is False


async def test_a_route_through_a_keep_out_zone_needs_the_operator(app, client, ready_asset):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://server",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    ) as admin:
        response = await admin.post(
            "/v1/zones",
            json={
                "name": "Fuel dump",
                "zone_type": "restricted",
                "geometry": [
                    {"latitude_deg": SITE_LAT + 0.0004, "longitude_deg": SITE_LON - 0.0005},
                    {"latitude_deg": SITE_LAT + 0.0008, "longitude_deg": SITE_LON - 0.0005},
                    {"latitude_deg": SITE_LAT + 0.0008, "longitude_deg": SITE_LON + 0.0005},
                    {"latitude_deg": SITE_LAT + 0.0004, "longitude_deg": SITE_LON + 0.0005},
                ],
            },
        )
        assert response.status_code == 201

    # Straight north from the machine, through the dump.
    crossing = await _preview(client, ready_asset.asset_id)
    keep_out = _by_id(crossing)["keep_out"]
    assert keep_out["state"] == "needs_you"
    assert keep_out["text"] == "This route crosses Fuel dump."
    assert "zone list" in keep_out["source"]
    assert crossing["can_send"] is True, "a keep-out is the operator's call, not a refusal"

    # East instead, well clear of it.
    clear = await _preview(
        client,
        ready_asset.asset_id,
        waypoints=[{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON + 0.002}],
    )
    keep_out = _by_id(clear)["keep_out"]
    assert keep_out["state"] == "pass"
    assert "zone list" in keep_out["source"]


async def test_a_zone_that_only_alerts_on_entry_is_still_a_keep_out(client, ready_asset, gate_zone):
    keep_out = _by_id(await _preview(client, ready_asset.asset_id))["keep_out"]
    assert keep_out["state"] == "needs_you"
    assert gate_zone.name in keep_out["text"]


async def test_a_zone_of_a_type_this_build_never_heard_of_is_an_open_question(
    app, client, ready_asset
):
    """The vocabulary is open. A newer station's word for closed must not
    be read as clear because this build never learned it."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://server",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    ) as admin:
        await admin.post(
            "/v1/zones",
            json={
                "name": "North paddock",
                "zone_type": "no_go",
                "geometry": [
                    {"latitude_deg": SITE_LAT + 0.0004, "longitude_deg": SITE_LON - 0.0005},
                    {"latitude_deg": SITE_LAT + 0.0008, "longitude_deg": SITE_LON - 0.0005},
                    {"latitude_deg": SITE_LAT + 0.0008, "longitude_deg": SITE_LON + 0.0005},
                    {"latitude_deg": SITE_LAT + 0.0004, "longitude_deg": SITE_LON + 0.0005},
                ],
            },
        )
    keep_out = _by_id(await _preview(client, ready_asset.asset_id))["keep_out"]
    assert keep_out["state"] == "unknown"
    assert keep_out["text"].startswith("This route crosses North paddock.")
    assert "no_go" not in keep_out["text"]


async def test_a_patrol_returns_to_where_it_started(client, ready_asset):
    first = {"latitude_deg": SITE_LAT + 0.001, "longitude_deg": SITE_LON}
    second = {"latitude_deg": SITE_LAT + 0.001, "longitude_deg": SITE_LON + 0.001}
    patrol = await _preview(client, ready_asset.asset_id, task_type="patrol", waypoints=[first, second])
    assert patrol["path"] == [{"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}, first, second, first]
    one_way = await _preview(client, ready_asset.asset_id, waypoints=[first, second])
    assert patrol["distance_m"] > one_way["distance_m"]


async def test_a_proposal_for_a_machine_we_do_not_have_is_a_404(client):
    response = await client.post(
        "/v1/tasks/preview", json={"asset_id": "nobody", "task_type": "navigate", "waypoints": []}
    )
    assert response.status_code == 404
    assert "not known" in response.json()["detail"]


async def test_a_proposal_reads_as_plain_words(client, store, ready_asset):
    for reading in (0.9, 0.1):
        ready_asset.battery_fraction = reading
        store.put_asset(ready_asset)
        preview = await _preview(client, ready_asset.asset_id, task_type="dig")
        for check in preview["checks"]:
            for field in ("text", "source"):
                assert ready_asset.asset_id not in check[field]
                assert not JARGON.search(check[field]), check[field]


# -- what a machine says about itself ----------------------------------------


async def test_a_machine_that_has_reported_nothing_gets_only_a_control_link_row(client, ready_asset):
    response = await client.get(f"/v1/assets/{ready_asset.asset_id}/systems")
    assert response.status_code == 200
    body = response.json()

    assert body["asset_id"] == ready_asset.asset_id
    assert body["reported_at"] is None
    assert [r["name"] for r in body["rows"]] == ["Control link"]
    assert body["rows"][0]["state"] == "ok"
    assert re.fullmatch(r"Heard \d+ s ago", body["rows"][0]["text"])
    assert body["cameras"] == []
    assert body["position_source"] is None
    assert body["note"] == "UGV-1 has not reported its systems."


async def test_a_silent_machine_shows_when_its_link_was_last_heard(client, store):
    quiet = Asset(asset_id=new_id(), asset_class="ugv", last_heartbeat=_stale())
    store.put_asset(quiet)
    body = (await client.get(f"/v1/assets/{quiet.asset_id}/systems")).json()
    link = body["rows"][0]
    assert link["state"] == "off"
    assert link["text"].startswith("Last heard ")
    assert " Z on " in link["text"]


async def test_the_registry_becomes_rows_an_operator_can_read(client, store, ready_asset):
    store.put_payload(
        ready_asset.asset_id,
        {
            "registry": {
                "drivers": [
                    {"name": "left_right_motors", "kind": "locomotion", "version": "1.2"},
                    {"name": "lte_modem", "kind": "comms", "version": "0.9"},
                    {"name": "front_stereo", "kind": "sensor", "version": "3.0", "streams": ["frames", "depth"]},
                    {"name": "gnss_fusion", "kind": "localization", "version": "0.1"},
                    {"name": "thermal_pod", "kind": "sensor", "version": "3.0"},
                ],
                "devices": [
                    {
                        "bus": "gmsl2",
                        "identifier": "imager-0",
                        "description": "front stereo imager",
                        "present": True,
                        "driver": "front_stereo",
                    },
                    {
                        "bus": "usb",
                        "identifier": "thermal-0",
                        "description": "thermal camera",
                        "present": False,
                        "driver": "thermal_pod",
                    },
                    {
                        "bus": "can",
                        "identifier": "motor-controller-0",
                        "description": "motor controller",
                        "present": True,
                        "driver": "left_right_motors",
                    },
                ],
                "health": [
                    {"driver": "left_right_motors", "healthy": True, "detail": ""},
                    {"driver": "lte_modem", "healthy": False, "detail": "no carrier on ttyUSB0"},
                    {"driver": "front_stereo", "healthy": True, "detail": ""},
                    {"driver": "thermal_pod", "healthy": True, "detail": ""},
                ],
            }
        },
    )

    body = (await client.get(f"/v1/assets/{ready_asset.asset_id}/systems")).json()
    rows = {r["name"]: r for r in body["rows"]}

    assert body["reported_at"] is not None
    assert list(rows) == [
        "Control link", "Drive", "Radio link", "Sensor 1", "Position fix", "Sensor 2"
    ]
    assert rows["Drive"]["state"] == "ok"
    assert rows["Radio link"]["state"] == "act"
    assert rows["Sensor 1"]["state"] == "ok"
    assert rows["Sensor 2"]["state"] == "warn", "healthy driver, but its hardware was not found"
    assert rows["Position fix"]["state"] == "unknown", "no health entry means no claim"

    # One found by the stream its driver declares, one by its description.
    assert [c["name"] for c in body["cameras"]] == ["front stereo imager", "thermal camera"]
    assert body["cameras"][0]["state"] == "ok"
    assert body["cameras"][1]["state"] == "off"

    assert body["position_source"] == "gnss fusion"
    assert body["note"].startswith("Reported by UGV-1 itself at ")

    # Nothing below the waterline reaches the operator.
    for row in body["rows"] + body["cameras"]:
        for field in ("name", "text"):
            assert "ttyUSB0" not in row[field]
            assert "_" not in row[field]
            assert "1.2" not in row[field]


async def test_a_registry_with_no_health_makes_no_health_claims(client, store, ready_asset):
    store.put_payload(
        ready_asset.asset_id,
        {"registry": {"drivers": [{"name": "wheels", "kind": "locomotion"}]}},
    )
    body = (await client.get(f"/v1/assets/{ready_asset.asset_id}/systems")).json()
    assert body["rows"][1] == {
        "name": "Drive", "state": "unknown", "text": "Has not said whether it is working."
    }


async def test_asking_about_a_machine_we_do_not_have_is_a_404(client):
    response = await client.get("/v1/assets/nobody/systems")
    assert response.status_code == 404
    assert "not known" in response.json()["detail"]


async def test_the_systems_summary_needs_a_caller_and_the_registry_still_needs_an_admin(
    app, client, ready_asset
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://server"
    ) as anonymous:
        assert (await anonymous.get(f"/v1/assets/{ready_asset.asset_id}/systems")).status_code == 401
    assert (await client.get(f"/v1/assets/{ready_asset.asset_id}/registry")).status_code == 403


# -- issuing follows the preview -----------------------------------------


@pytest.mark.asyncio
async def test_an_order_is_refused_for_a_machine_that_has_gone_quiet(client, store, ready_asset):
    """What the preview calls a failed "answering" check, issue refuses too."""
    ready_asset.last_heartbeat.CopyFrom(_stale())
    store.put_asset(ready_asset)
    body = {"asset_id": ready_asset.asset_id, "task_type": "navigate",
            "waypoints": [{"latitude_deg": SITE_LAT + 0.001, "longitude_deg": SITE_LON}]}
    response = await client.post("/v1/tasks", json=body, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    assert response.status_code == 409
    preview = await _preview(client, ready_asset.asset_id)
    answering = _by_id(preview)["answering"]
    assert answering["state"] == "fail"
    # Refused in the check's own words, so the person reads one reason.
    assert response.json()["detail"] == answering["text"]


# -- issuing runs the preview's checks again, against the world now ---------


ISSUER = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


async def _issue(client, asset_id: str, task_type: str = "navigate", waypoints=None):
    return await client.post(
        "/v1/tasks",
        json={
            "asset_id": asset_id,
            "task_type": task_type,
            "waypoints": waypoints
            if waypoints is not None
            else [{"latitude_deg": SITE_LAT + 0.001, "longitude_deg": SITE_LON}],
        },
        headers=ISSUER,
    )


def _orders_sent(transport, settings, asset_id: str) -> list:
    return [t for t, _ in transport.published if t == f"{settings.topic_prefix}/{asset_id}/task"]


async def _add_zone(app, name: str, zone_type: str, south: float, north: float) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://server", headers=ISSUER
    ) as admin:
        response = await admin.post(
            "/v1/zones",
            json={
                "name": name,
                "zone_type": zone_type,
                "geometry": [
                    {"latitude_deg": south, "longitude_deg": SITE_LON - 0.0005},
                    {"latitude_deg": north, "longitude_deg": SITE_LON - 0.0005},
                    {"latitude_deg": north, "longitude_deg": SITE_LON + 0.0005},
                    {"latitude_deg": south, "longitude_deg": SITE_LON + 0.0005},
                ],
            },
        )
        assert response.status_code == 201, response.text


async def test_support_withdrawn_after_the_preview_refuses_the_order_in_the_checks_words(
    client, store, transport, settings, ready_asset
):
    """The operator approved a proposal whose checks have since changed.
    The order is judged against the machine as it is now."""
    assert (await _preview(client, ready_asset.asset_id))["can_send"] is True

    ready_asset.capabilities.update({"supported_task_types": "patrol"})
    store.put_asset(ready_asset)

    response = await _issue(client, ready_asset.asset_id)
    assert response.status_code == 409
    supports = _by_id(await _preview(client, ready_asset.asset_id))["supports"]
    assert supports["state"] == "fail"
    assert response.json()["detail"] == supports["text"]
    assert store.list_tasks() == []
    assert _orders_sent(transport, settings, ready_asset.asset_id) == []


async def test_an_order_to_a_machine_never_heard_from_is_refused(client, store, transport, settings):
    """The preview fails a machine that has never answered. Issuing agrees."""
    unheard = Asset(asset_id=new_id(), asset_class="ugv")
    unheard.capabilities.update({"name": "Scout 9"})
    store.put_asset(unheard)

    response = await _issue(client, unheard.asset_id)
    assert response.status_code == 409
    assert response.json()["detail"] == "Scout 9 has never answered."
    assert store.list_tasks() == []
    assert _orders_sent(transport, settings, unheard.asset_id) == []


async def test_a_battery_that_drops_after_the_preview_is_judged_as_a_fresh_preview_judges_it(
    client, store, transport, settings, ready_asset
):
    """A low battery is amber in the preview, the operator's call, and never
    a refusal. Issuing applies the same rule, read from the battery now."""
    assert _by_id(await _preview(client, ready_asset.asset_id))["battery"]["state"] == "pass"

    ready_asset.battery_fraction = 0.05
    store.put_asset(ready_asset)
    fresh = await _preview(client, ready_asset.asset_id)
    assert _by_id(fresh)["battery"]["state"] == "needs_you"

    response = await _issue(client, ready_asset.asset_id)
    assert (response.status_code == 409) == (not fresh["can_send"])


async def test_a_keep_out_added_after_the_preview_is_judged_as_a_fresh_preview_judges_it(
    app, client, store, ready_asset
):
    """A route across a keep-out is amber, the operator's call. Issuing
    reads the zone list as it is now, not as it was at the preview."""
    assert _by_id(await _preview(client, ready_asset.asset_id))["keep_out"]["state"] == "pass"

    await _add_zone(app, "Fuel dump", "restricted", SITE_LAT + 0.0004, SITE_LAT + 0.0008)
    fresh = await _preview(client, ready_asset.asset_id)
    assert _by_id(fresh)["keep_out"]["state"] == "needs_you"

    response = await _issue(client, ready_asset.asset_id)
    assert (response.status_code == 409) == (not fresh["can_send"])


@pytest.mark.parametrize(
    "change",
    ["nothing", "battery", "keep_out", "supports", "quiet", "offline", "automatic", "unknown_mode"],
)
async def test_issuing_refuses_exactly_when_a_fresh_preview_would(
    app, client, store, transport, settings, ready_asset, change
):
    """One set of checks, two callers. Whatever the world does between the
    proposal and the approval, the order goes if and only if a proposal
    taken at that moment could be sent, and a refusal reads as the first
    failing check does."""
    if change == "battery":
        ready_asset.battery_fraction = 0.05
    elif change == "supports":
        ready_asset.capabilities.update({"supported_task_types": "patrol"})
    elif change == "quiet":
        ready_asset.last_heartbeat.CopyFrom(_stale())
    elif change == "offline":
        ready_asset.status = AssetStatus.ASSET_STATUS_OFFLINE
    store.put_asset(ready_asset)
    if change == "keep_out":
        await _add_zone(app, "Fuel dump", "restricted", SITE_LAT + 0.0004, SITE_LAT + 0.0008)
    elif change == "automatic":
        store.set_autonomy(ready_asset.asset_id, "automatic", "someone")
    elif change == "unknown_mode":
        store.set_autonomy(ready_asset.asset_id, "supervised", "someone")

    fresh = await _preview(client, ready_asset.asset_id)
    response = await _issue(client, ready_asset.asset_id)

    if fresh["can_send"]:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 409
        first_fail = next(c for c in fresh["checks"] if c["state"] == "fail")
        assert response.json()["detail"] == first_fail["text"]
        assert store.list_tasks() == []
        assert _orders_sent(transport, settings, ready_asset.asset_id) == []


# -- a route from a place nobody knows ---------------------------------------


@pytest.fixture
def lost_asset(store) -> Asset:
    """Answering and ready, but it has never said where it is."""
    asset = Asset(
        asset_id=new_id(),
        asset_class="ugv",
        status=AssetStatus.ASSET_STATUS_ACTIVE,
        last_heartbeat=now_ts(),
        battery_fraction=0.9,
    )
    asset.capabilities.update(
        {"name": "UGV-2", "max_speed_mps": 2.0, "supported_task_types": "navigate, patrol"}
    )
    store.put_asset(asset)
    return asset


async def test_with_no_known_start_the_way_there_is_not_called_clear(app, client, lost_asset):
    """A keep-out between the machine and its destination cannot be ruled
    out, and a distance from nowhere is not zero."""
    await _add_zone(app, "Fuel dump", "restricted", SITE_LAT + 0.0004, SITE_LAT + 0.0008)
    # Beyond the dump, not inside it.
    preview = await _preview(
        client,
        lost_asset.asset_id,
        waypoints=[{"latitude_deg": SITE_LAT + 0.002, "longitude_deg": SITE_LON}],
    )
    keep_out = _by_id(preview)["keep_out"]
    assert keep_out["state"] == "unknown"
    assert keep_out["text"] == "UGV-2 has not said where it is, so the way there was not checked."
    assert "zone list" in keep_out["source"]
    assert preview["distance_m"] is None
    assert preview["eta_sec"] is None
    assert preview["speed_mps_assumed"] is None
    assert preview["can_send"] is True, "an unknown is the operator's call, not a refusal"


async def test_with_no_known_start_a_destination_inside_a_keep_out_still_crosses_it(
    app, client, lost_asset
):
    """Not knowing where the machine is does not make a closed destination
    any less closed."""
    await _add_zone(app, "Fuel dump", "restricted", SITE_LAT + 0.0004, SITE_LAT + 0.0008)
    preview = await _preview(
        client,
        lost_asset.asset_id,
        waypoints=[{"latitude_deg": SITE_LAT + 0.0006, "longitude_deg": SITE_LON}],
    )
    keep_out = _by_id(preview)["keep_out"]
    assert keep_out["state"] == "needs_you"
    assert keep_out["text"] == "This route crosses Fuel dump."


async def test_with_no_known_start_and_no_zones_the_route_is_still_clear(client, lost_asset):
    """With no keep-out anywhere, there is nothing the way there could cross."""
    preview = await _preview(client, lost_asset.asset_id)
    assert _by_id(preview)["keep_out"]["state"] == "pass"
    assert preview["distance_m"] is None
