"""The loop that guards every change.

This is the definition of done for the world model plus the fake army: a
simulated vehicle appears, moves, produces observations that become visible
tracks, accepts an order issued the way an operator issues one, and reports
progress to completion. Then it is killed mid-order and the system notices.

Any commit that breaks this test is a broken commit.
"""

from __future__ import annotations

from link.v1.ontology_pb2 import AssetStatus, Observation, Position, TaskState

from sim.link_client import LinkClient
from sim.transport import DirectVehicleLink
from sim.vehicle import ScriptedObservation
from track.ids import new_id, now_ts

from tests.conftest import SITE_LAT, SITE_LON, wait_until

# About 60 meters north of the start, so a fast vehicle covers it in seconds.
WAYPOINT_NORTH = {"latitude_deg": SITE_LAT + 0.00054, "longitude_deg": SITE_LON}
# Far enough that the vehicle is still driving when we kill it.
WAYPOINT_FAR = {"latitude_deg": SITE_LAT + 0.02, "longitude_deg": SITE_LON}


def a_person_nearby() -> ScriptedObservation:
    return ScriptedObservation(
        after_seconds=0.3,
        entity_class="person",
        confidence=0.45,
        offset_north_m=20,
        offset_east_m=6,
        narration="possible person near the fence line, low confidence",
        repeat_every_seconds=0.3,
        count=8,
    )


async def test_the_full_task_loop(client, world, make_vehicle):
    updates = world.bus.subscribe()
    vehicle = make_vehicle(observations=[a_person_nearby()])
    vehicle.start()

    # 1. It appears, through the same interface an application would use.
    await wait_until(lambda: world.store.get_asset(vehicle.asset_id) is not None)
    listed = (await client.get("/v1/assets")).json()
    assert [a["asset_id"] for a in listed] == [vehicle.asset_id]
    assert listed[0]["asset_class"] == "ugv"

    online = await wait_until(
        lambda: [e for e in world.store.list_events() if "online" in e.text.lower()]
    )
    assert "healthy" in online[0].text.lower()

    # 2. It moves, and its motion is available live.
    await wait_until(lambda: vehicle.asset_id in world.telemetry)

    # 3. What it sees becomes a track, visible through the public interface.
    await wait_until(lambda: world.store.list_tracks())
    tracks = (await client.get("/v1/tracks")).json()
    assert len(tracks) == 1
    assert tracks[0]["state"] == "TRACK_STATE_ACTIVE"

    detection = await wait_until(
        lambda: [e for e in world.store.list_events() if "person" in e.text.lower()]
    )
    # The honesty law, end to end: a weak detection reads as a weak detection.
    assert "possible" in detection[0].text.lower()
    assert "low confidence" in detection[0].text.lower()

    # 4. An order issued the way the map issues one, run to completion.
    created = await client.post(
        "/v1/tasks",
        json={
            "asset_id": vehicle.asset_id,
            "task_type": "navigate",
            "waypoints": [WAYPOINT_NORTH],
            "channel": "map",
        },
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]

    finished = await wait_until(
        lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_DONE, timeout=20
    )
    assert finished

    task = world.store.get_task(task_id)
    states = [change.state for change in task.status_history]
    assert TaskState.TASK_STATE_PENDING in states
    assert TaskState.TASK_STATE_ACCEPTED in states
    assert TaskState.TASK_STATE_RUNNING in states
    assert states[-1] == TaskState.TASK_STATE_DONE

    # It really travelled: the last position is near the waypoint, not the start.
    assert world.store.get_asset(vehicle.asset_id).position.latitude_deg > SITE_LAT + 0.0004

    # Progress was reported along the way, not only at the end.
    seen = drain(updates)
    progress_values = [
        m["data"]["progress"]
        for m in seen
        if m["kind"] == "task.updated" and 0.0 < m["data"]["progress"] < 1.0
    ]
    assert progress_values, "the vehicle never reported partial progress"
    assert any(m["kind"] == "event.created" for m in seen)


async def test_killing_the_vehicle_turns_it_grey_and_fails_its_order(client, world, make_vehicle):
    # Slow, so the order is still running when the vehicle dies.
    vehicle = make_vehicle(speed_mps=1.0)
    vehicle.start()
    await wait_until(lambda: world.store.get_asset(vehicle.asset_id) is not None)

    created = await client.post(
        "/v1/tasks",
        json={
            "asset_id": vehicle.asset_id,
            "task_type": "navigate",
            "waypoints": [WAYPOINT_FAR],
            "channel": "map",
        },
    )
    task_id = created.json()["task_id"]
    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_RUNNING)

    vehicle.stop()

    await wait_until(
        lambda: world.store.get_asset(vehicle.asset_id).status == AssetStatus.ASSET_STATUS_OFFLINE
    )
    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_FAILED)

    # The operator is told, in words, what happened and why.
    texts = [e.text.lower() for e in world.store.list_events()]
    assert any("stopped answering" in t for t in texts)
    assert any("could not" in t for t in texts)

    failure = world.store.get_task(task_id).status_history[-1]
    assert failure.state == TaskState.TASK_STATE_FAILED
    assert failure.message

    # The machine's last position is kept rather than erased.
    assert world.store.get_asset(vehicle.asset_id).position.latitude_deg >= SITE_LAT


async def test_an_order_it_cannot_carry_out_is_refused_not_ignored(client, world, make_vehicle):
    vehicle = make_vehicle()
    vehicle.start()
    await wait_until(lambda: world.store.get_asset(vehicle.asset_id) is not None)

    created = await client.post(
        "/v1/tasks",
        json={"asset_id": vehicle.asset_id, "task_type": "launch_torpedo", "channel": "map"},
    )
    task_id = created.json()["task_id"]

    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_FAILED)
    assert "cannot" in world.store.get_task(task_id).status_history[-1].message.lower()


async def test_observations_survive_an_outage(world, transport, settings):
    """The disconnection law: losing the link loses nothing that mattered."""
    asset_id = new_id()
    link = DirectVehicleLink(transport)
    client = LinkClient(asset_id, link, settings.topic_prefix, on_task=lambda _: None)
    client.start()

    link.drop()
    for _ in range(3):
        client.observation(
            Observation(
                observation_id=new_id(),
                entity_id=new_id(),
                asset_id=asset_id,
                position=Position(latitude_deg=SITE_LAT, longitude_deg=SITE_LON),
                confidence=0.7,
                entity_class="person",
                timestamp=now_ts(),
            )
        )

    assert client.held == 3
    assert world.store.list_observations() == []

    link.restore()
    await wait_until(lambda: len(world.store.list_observations()) == 3)
    assert client.held == 0


# -- helpers ---------------------------------------------------------------


def drain(subscription) -> list[dict]:
    messages = []
    while not subscription.queue.empty():
        messages.append(subscription.queue.get_nowait())
    return messages


# ------------------------------------ capabilities come from data, not code
async def test_what_it_can_do_is_scenario_data_and_reaches_the_world_model(
    client, world, make_vehicle
):
    """One source of truth for what a machine can do (the reverse-modeling
    fix): the scenario's declaration drives both the vehicle's own
    accept/refuse behavior and what TRACK believes about it. Change the
    data and the machine changes; no code changed hands."""
    vehicle = make_vehicle(supported_task_types=("navigate", "hold"))
    vehicle.start()
    await wait_until(lambda: world.store.get_asset(vehicle.asset_id) is not None)

    # The declaration reached the world model through the contract's
    # registry-in-telemetry convention, comma-joined like every machine's.
    def declared():
        asset = world.store.get_asset(vehicle.asset_id)
        if not asset.HasField("capabilities"):
            return None
        field = asset.capabilities.fields.get("supported_task_types")
        return field.string_value if field is not None else None

    assert await wait_until(lambda: declared() == "navigate, hold")

    # And the machine's behavior is the same truth: patrol, supported by
    # every default vehicle, is refused by this one, in words.
    created = await client.post(
        "/v1/tasks",
        json={
            "asset_id": vehicle.asset_id,
            "task_type": "patrol",
            "waypoints": [
                {"latitude_deg": SITE_LAT + 0.0005, "longitude_deg": SITE_LON},
                {"latitude_deg": SITE_LAT + 0.0005, "longitude_deg": SITE_LON + 0.0005},
            ],
            "channel": "map",
        },
    )
    task_id = created.json()["task_id"]
    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_FAILED)
    assert "cannot" in world.store.get_task(task_id).status_history[-1].message.lower()


async def test_a_scenario_file_carries_the_task_types(tmp_path):
    """The loader accepts the list form and the manifest's comma form."""
    import yaml

    from sim.scenario import load

    scenario = {
        "asset": {
            "asset_id": "01SIMTEST00000000000000001",
            "asset_class": "ugv",
            "name": "Listy",
            "capabilities": {"supported_task_types": ["navigate", "hold"]},
        },
        "start": {"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON},
    }
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump(scenario))
    cfg = load(p)
    assert cfg.supported_task_types == ("navigate", "hold")
    assert cfg.declared_capabilities()["supported_task_types"] == "navigate, hold"

    scenario["asset"]["capabilities"]["supported_task_types"] = "patrol, return_home"
    p.write_text(yaml.safe_dump(scenario))
    cfg = load(p)
    assert cfg.supported_task_types == ("patrol", "return_home")

    # Absent entirely: the classic four, unchanged behavior.
    del scenario["asset"]["capabilities"]["supported_task_types"]
    p.write_text(yaml.safe_dump(scenario))
    cfg = load(p)
    assert cfg.supported_task_types == ("navigate", "patrol", "hold", "return_home")


async def test_the_declaration_survives_a_link_that_is_down_at_boot(
    client, world, make_vehicle
):
    """A stale position is worthless a second later; a declaration the
    platform never received stays missing forever. So the client keeps
    the declaration and repeats it on every connect, the way the
    convention says a registry travels (link/CONVENTIONS.md section 1).
    Restoring the link alone must be enough; no one calls flush here."""
    vehicle = make_vehicle(supported_task_types=("navigate", "hold"))
    # The link is down when the run loop boots, as it is against a real
    # broker whose async connect has not completed yet.
    vehicle.client.start()
    vehicle.link.drop()
    vehicle._thread.start()

    # The vehicle boots and declares into a dead link; nothing arrives.
    await wait_until(lambda: vehicle.client._declaration is not None)
    assert world.store.get_asset(vehicle.asset_id) is None

    vehicle.link.restore()

    def declared():
        asset = world.store.get_asset(vehicle.asset_id)
        if asset is None or not asset.HasField("capabilities"):
            return None
        field = asset.capabilities.fields.get("supported_task_types")
        return field.string_value if field is not None else None

    assert await wait_until(lambda: declared() == "navigate, hold")
