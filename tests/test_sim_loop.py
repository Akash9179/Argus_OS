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
