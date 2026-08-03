"""Autonomy: what this platform may do with a machine without being asked.

Plan decision 10, stage one. The mode used to be a setting in one browser
tab, which meant no other station could see it, a reload lost it, nothing
enforced it, and every sentence about it had to be hedged into "this
station will..." because a browser cannot promise what a fleet does.

These tests are about the two halves that matter: the platform holds the
mode honestly (refusing what it cannot enforce, defaulting to doing
nothing), and the platform acts on it correctly (sending one machine,
choosing which, and taking back only its own orders).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from link.v1.ontology_pb2 import (
    Asset,
    AssetStatus,
    Entity,
    Issuer,
    Position,
    TaskParameters,
    Track,
)

from track.ids import new_id, now_ts

from tests.conftest import OPERATOR_TOKEN, SITE_LAT, SITE_LON


def an_asset(store, name: str, north_m: float = 0.0, **changes) -> Asset:
    """A machine on the map, offset north of the site by some metres."""
    asset = Asset(
        asset_id=new_id(),
        asset_class="ugv",
        status=changes.pop("status", AssetStatus.ASSET_STATUS_ACTIVE),
        last_heartbeat=now_ts(),
        position=Position(
            latitude_deg=SITE_LAT + north_m / 111_320.0, longitude_deg=SITE_LON
        ),
    )
    asset.capabilities.update({"name": name})
    store.put_asset(asset)
    return asset


def a_contact(store, north_m: float = 0.0) -> Track:
    entity = Entity(entity_id=new_id(), entity_class="person")
    store.put_entity(entity)
    track = Track(
        track_id=new_id(),
        entity_id=entity.entity_id,
        confidence=0.42,
        position=Position(
            latitude_deg=SITE_LAT + north_m / 111_320.0, longitude_deg=SITE_LON
        ),
    )
    store.put_track(track)
    return track


def open_tasks(world, asset_id: str) -> list:
    from track.worldmodel import OPEN_TASK_STATES

    return [
        t
        for t in world.store.list_tasks(asset_id=asset_id)
        if t.status in OPEN_TASK_STATES
    ]


# -- the platform holds the mode -------------------------------------------


async def test_a_machine_nobody_has_decided_about_does_nothing_on_its_own(client, world):
    """The default is not a convenience. A machine that acted because no
    row existed would be the platform taking an action nobody chose."""
    asset = an_asset(world.store, "Undecided")
    view = (await client.get(f"/v1/assets/{asset.asset_id}")).json()
    assert view["autonomy"] == "manual"

    await world.investigate(a_contact(world.store))
    assert open_tasks(world, asset.asset_id) == []


async def test_a_mode_the_platform_cannot_enforce_is_refused_not_stored(client, world):
    """A setting the system cannot honour is not a setting, it is a false
    claim on an operator's screen. Same reasoning as a misspelled AI
    policy profile being refused at startup."""
    asset = an_asset(world.store, "Scout")
    response = await client.put(
        f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "aggressive"}
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "Manual" in detail and "Automatic" in detail
    assert "aggressive" not in detail.lower() or "no setting called" in detail.lower()
    assert world.autonomy_of(asset.asset_id) == "manual", "a refused mode must not be stored"


async def test_the_mode_reaches_every_application_that_asks(client, world):
    asset = an_asset(world.store, "Scout")
    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    listed = {a["asset_id"]: a for a in (await client.get("/v1/assets")).json()}
    assert listed[asset.asset_id]["autonomy"] == "automatic"
    one = (await client.get(f"/v1/assets/{asset.asset_id}")).json()
    assert one["autonomy"] == "automatic"


async def test_switching_the_mode_says_so_in_the_feed_and_names_the_person(client, world):
    asset = an_asset(world.store, "Scout")
    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    events = (await client.get("/v1/events")).json()
    switched = [e for e in events if e["subject_id"] == asset.asset_id and "now" in e["text"]]
    assert switched, "switching a machine's mode belongs in the feed"
    assert "Changed by Test Operator" == switched[0]["source"]
    assert "automatic" not in switched[0]["text"].lower(), (
        "the sentence says what will happen, not the code word for the setting"
    )
    assert switched[0]["severity"] == "attention", "going automatic is worth noticing"


async def test_setting_a_mode_needs_a_key(app, world):
    import httpx

    asset = an_asset(world.store, "Scout")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://server"
    ) as anonymous:
        refused = await anonymous.put(
            f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"}
        )
    assert refused.status_code == 401


# -- the platform acts on the mode -----------------------------------------


async def test_an_automatic_machine_is_sent_to_look_and_nobody_is_credited(client, world):
    """The order goes through the same single path a map click uses, and
    names nobody on every surface, because no person gave it."""
    asset = an_asset(world.store, "Scout")
    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    await world.investigate(a_contact(world.store, north_m=30))

    running = open_tasks(world, asset.asset_id)
    assert len(running) == 1, "one machine per contact, never a swarm"
    view = world.task_view(running[0])
    assert view["issued_by"]["channel"] == "automatic"
    assert view["ordered_by"] == ""
    assert "without anyone being asked" in view["reason"]

    sources = [e["source"] for e in (await client.get("/v1/events")).json()]
    assert any("Ordered automatically, without being asked" == s for s in sources)
    assert not any("Ordered by Test Operator" == s for s in sources), (
        "the operator did not give this order and must not be credited with it"
    )


async def test_a_manual_machine_is_never_sent_anywhere(client, world):
    manual = an_asset(world.store, "Waiting")
    await world.investigate(a_contact(world.store, north_m=30))
    assert open_tasks(world, manual.asset_id) == []


async def test_the_nearest_eligible_machine_goes(client, world):
    """Which machine goes is the platform's call, because only the platform
    holds the fused picture. A station's idea of the selected machine is a
    fact about a browser tab."""
    near = an_asset(world.store, "Near", north_m=50)
    far = an_asset(world.store, "Far", north_m=900)
    for asset in (near, far):
        await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    await world.investigate(a_contact(world.store, north_m=60))

    assert len(open_tasks(world, near.asset_id)) == 1
    assert open_tasks(world, far.asset_id) == [], "only one machine goes"


async def test_a_machine_already_carrying_an_order_is_left_alone(client, world):
    busy = an_asset(world.store, "Busy")
    spare = an_asset(world.store, "Spare", north_m=800)
    for asset in (busy, spare):
        await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    await world.issue_task(
        asset_id=busy.asset_id,
        task_type="navigate",
        parameters=TaskParameters(waypoints=[Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON)]),
        issuer=Issuer(principal_id="operator-1", channel="map"),
    )
    await world.investigate(a_contact(world.store, north_m=10))

    assert len(open_tasks(world, busy.asset_id)) == 1, "its existing work is not replaced"
    assert len(open_tasks(world, spare.asset_id)) == 1, "the free machine went instead"


async def test_a_contact_is_investigated_once_even_across_a_restart(client, world):
    """The record is persistent so a restart does not send machines out
    again to contacts that were looked at hours ago."""
    asset = an_asset(world.store, "Scout")
    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})
    track = a_contact(world.store, north_m=30)

    await world.investigate(track)
    assert world.store.was_investigated(track.track_id)

    # Finish the order, then offer the same contact again.
    for task in world.store.list_tasks(asset_id=asset.asset_id):
        await world.cancel_task(task.task_id)
    await world.investigate(track)

    assert open_tasks(world, asset.asset_id) == [], "already looked at"


async def test_switching_to_automatic_looks_at_contacts_already_on_the_map(client, world):
    """The setting takes effect on what is already there, not only on the
    next contact to appear."""
    asset = an_asset(world.store, "Scout")
    a_contact(world.store, north_m=40)

    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    assert len(open_tasks(world, asset.asset_id)) == 1


async def test_going_manual_withdraws_the_platforms_own_order(client, world):
    asset = an_asset(world.store, "Scout")
    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})
    await world.investigate(a_contact(world.store, north_m=30))
    assert len(open_tasks(world, asset.asset_id)) == 1

    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "manual"})
    assert open_tasks(world, asset.asset_id) == []


async def test_going_manual_leaves_an_operators_order_running(client, world):
    """The server-side descendant of the C2 bug: an order belongs to
    whoever gave it, and taking it back because a mode changed would be
    the platform acting on somebody else's behalf."""
    asset = an_asset(world.store, "Scout")
    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    mine = await world.issue_task(
        asset_id=asset.asset_id,
        task_type="navigate",
        parameters=TaskParameters(waypoints=[Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON)]),
        issuer=Issuer(principal_id="operator-1", channel="map"),
    )

    await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "manual"})

    still = [t.task_id for t in open_tasks(world, asset.asset_id)]
    assert mine.task_id in still, "an operator's order is not the platform's to withdraw"


async def test_a_machine_that_is_not_answering_is_never_sent(client, world):
    quiet = an_asset(world.store, "Quiet", status=AssetStatus.ASSET_STATUS_OFFLINE)
    await client.put(f"/v1/assets/{quiet.asset_id}/autonomy", json={"mode": "automatic"})

    await world.investigate(a_contact(world.store, north_m=30))
    assert open_tasks(world, quiet.asset_id) == []


async def test_a_real_sighting_sends_a_machine_without_anyone_clicking(
    client, world, make_vehicle
):
    """The wiring, end to end, through the ingest path rather than the
    engine's front door. A machine reports something it saw, fusion opens a
    contact, and the platform sends a machine to look, with no operator
    involved at any point.
    """
    from sim.vehicle import ScriptedObservation

    from tests.conftest import wait_until

    watcher = make_vehicle(
        observations=[
            ScriptedObservation(
                after_seconds=0.3,
                entity_class="person",
                confidence=0.45,
                offset_north_m=20,
                narration="possible person near the fence line, low confidence",
            )
        ]
    )
    watcher.start()
    await wait_until(lambda: world.store.get_asset(watcher.asset_id) is not None)
    await client.put(
        f"/v1/assets/{watcher.asset_id}/autonomy", json={"mode": "automatic"}
    )

    await wait_until(lambda: bool(open_tasks(world, watcher.asset_id)))

    ordered = open_tasks(world, watcher.asset_id)[0]
    assert world.task_view(ordered)["ordered_by"] == ""
    assert world.store.was_investigated(
        world.store.list_tracks(limit=10)[0].track_id
    ), "the contact is recorded as looked at, so it is not looked at twice"


def test_a_mode_the_language_file_invents_is_refused_at_startup(settings, store, transport, bus):
    """A mode nothing implements is a setting an operator can select and
    the platform will silently ignore. Refused where somebody is looking,
    not on the first operator who picks it."""
    from track.events import Language
    from track.worldmodel import WorldModel, check_autonomy_language

    data = yaml.safe_load(Path(settings.event_templates_path).read_text())
    data["autonomy_modes"]["aggressive"] = "Aggressive"

    with pytest.raises(ValueError) as refused:
        check_autonomy_language(Language(data))
    assert "aggressive" in str(refused.value)

    with pytest.raises(ValueError):
        WorldModel(store, settings, transport, bus, language=Language(data))


def test_a_mode_with_no_sentence_or_no_colour_is_refused_at_startup(settings):
    """Switching to a mode with no sentence raises after the change has
    already been written, and a mode with no colour reads as routine when
    it is anything but. Both are checked before they can happen."""
    from track.events import Language
    from track.worldmodel import check_autonomy_language

    data = yaml.safe_load(Path(settings.event_templates_path).read_text())
    del data["templates"]["autonomy_automatic"]

    with pytest.raises(ValueError) as refused:
        check_autonomy_language(Language(data))
    assert "no sentence" in str(refused.value)


async def test_a_machine_that_cannot_be_told_to_navigate_is_not_sent(client, world):
    """Read from what the machine declared, never from what kind of thing
    it is: branching on asset_class here would put vehicle specifics above
    the hardware abstraction layer."""
    watcher = an_asset(world.store, "Fixed camera", north_m=10)
    watcher.capabilities.update({"supported_task_types": "hold, observe"})
    world.store.put_asset(watcher)
    driver = an_asset(world.store, "Scout", north_m=700)
    driver.capabilities.update({"supported_task_types": "navigate, hold"})
    world.store.put_asset(driver)

    for asset in (watcher, driver):
        await client.put(f"/v1/assets/{asset.asset_id}/autonomy", json={"mode": "automatic"})

    await world.investigate(a_contact(world.store, north_m=12))

    assert open_tasks(world, watcher.asset_id) == [], (
        "it said it cannot be told to navigate, so it is not told to"
    )
    assert len(open_tasks(world, driver.asset_id)) == 1, "the machine that can, goes"


async def test_a_machine_that_declares_nothing_is_still_eligible(client, world):
    """The server does not police the vocabulary. A machine that declares
    no supported types refuses for itself, the same rule the tasking
    endpoint already follows."""
    quiet = an_asset(world.store, "Undeclared")
    await client.put(f"/v1/assets/{quiet.asset_id}/autonomy", json={"mode": "automatic"})

    await world.investigate(a_contact(world.store, north_m=20))
    assert len(open_tasks(world, quiet.asset_id)) == 1


async def test_a_busy_machine_is_seen_even_beyond_the_recent_task_window(client, world):
    """The busy check must be exact. Counting only recent tasks let a
    machine carrying an operator's order be re-tasked once enough other
    orders had been written."""
    busy = an_asset(world.store, "Busy")
    await client.put(f"/v1/assets/{busy.asset_id}/autonomy", json={"mode": "automatic"})

    await world.issue_task(
        asset_id=busy.asset_id,
        task_type="navigate",
        parameters=TaskParameters(waypoints=[Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON)]),
        issuer=Issuer(principal_id="operator-1", channel="map"),
    )
    # Bury it under plenty of finished orders from another machine.
    other = an_asset(world.store, "Other", north_m=2000)
    for _ in range(60):
        done = await world.issue_task(
            asset_id=other.asset_id,
            task_type="navigate",
            parameters=TaskParameters(waypoints=[Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON)]),
            issuer=Issuer(principal_id="operator-1", channel="map"),
        )
        await world.cancel_task(done.task_id)

    await world.investigate(a_contact(world.store, north_m=5))
    assert len(open_tasks(world, busy.asset_id)) == 1, "its operator's order was not replaced"


def test_a_mode_with_no_colour_is_refused_at_startup(settings):
    """A mode that lets the platform act unasked is not routine, and an
    event with no colour falls back to exactly that."""
    from track.events import Language
    from track.worldmodel import check_autonomy_language

    data = yaml.safe_load(Path(settings.event_templates_path).read_text())
    del data["severity"]["autonomy_automatic"]

    with pytest.raises(ValueError) as refused:
        check_autonomy_language(Language(data))
    assert "colour" in str(refused.value)
