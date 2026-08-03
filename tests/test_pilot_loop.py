"""Stage 3A's definition of done, as a test.

Five criteria, one file. The edge runtime with no hardware behind it must
be a machine the world model treats like any other, must carry out an order
from the map, must keep working and lose nothing when the link drops, must
change its behaviour when handed a different machine's manifest without a
line of code changing, and must be able to say what it is made of.

Any commit that breaks this test is a broken commit, for the same reason
the simulated vehicle's loop is: it is not a test of a feature, it is the
stage.
"""

from __future__ import annotations

from link.v1.messages_pb2 import Heartbeat, Telemetry
from link.v1.ontology_pb2 import AssetStatus, TaskState

from tests.conftest import (
    ADMIN_TOKEN,
    SITE_LAT,
    SITE_LON,
    a_camera_seeing_a_person,
    a_manifest,
    wait_until,
)

# About 60 meters north of the start, so a fast machine covers it in seconds.
WAYPOINT_NORTH = {"latitude_deg": SITE_LAT + 0.00054, "longitude_deg": SITE_LON}
# Far enough that the machine is still driving when the link is cut.
WAYPOINT_FAR = {"latitude_deg": SITE_LAT + 0.02, "longitude_deg": SITE_LON}


# -- criterion 1 -----------------------------------------------------------


async def test_the_server_treats_it_as_an_ordinary_machine(
    client, world, transport, make_machine
):
    """Nothing about the runtime asks the server to know it is a runtime.

    The point is not that PILOT and the simulated vehicle send identical
    bytes; they are different machines with different names. It is that
    every message PILOT sends is a fully formed contract message on the
    same topics with the same versions, so the world model has no code path
    for it and nothing marks it as running on simulated hardware.
    """
    machine = make_machine(a_manifest(name="Runtime machine"))
    machine.start()

    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    # It appears through the interface an application uses, with the name it
    # declared for itself rather than one composed on its behalf.
    listed = (await client.get("/v1/assets")).json()
    mine = [a for a in listed if a["asset_id"] == machine.asset_id]
    assert len(mine) == 1
    assert mine[0]["asset_class"] == "ugv"

    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)
    listed = (await client.get("/v1/assets")).json()
    mine = [a for a in listed if a["asset_id"] == machine.asset_id]
    assert mine[0]["display_name"] == "Runtime machine"

    # Every message it put on the wire is a valid contract message carrying
    # the frozen versions, and none of them says anything about simulation.
    mine_topics = [
        (topic, payload) for topic, payload in transport.published if machine.asset_id in topic
    ]
    assert mine_topics, "the machine never spoke"

    kinds = {topic.rsplit("/", 1)[1] for topic, _ in mine_topics}
    assert "heartbeat" in kinds
    assert "telemetry" in kinds

    for topic, payload in mine_topics:
        kind = topic.rsplit("/", 1)[1]
        if kind == "heartbeat":
            msg = Heartbeat.FromString(payload)
        elif kind == "telemetry":
            msg = Telemetry.FromString(payload)
        else:
            continue
        assert msg.link_version == 1
        assert msg.ontology_version == 1
        assert msg.asset_id == machine.asset_id

        # Nothing in what the machine reports about its own state marks it
        # as running on simulated hardware. The registry is deliberately
        # excluded here and checked separately below: a machine saying its
        # drivers are simulated is the honesty law working, not a covert
        # marker, and an operator is entitled to that answer.
        state_only = Telemetry.FromString(payload) if kind == "telemetry" else msg
        if kind == "telemetry":
            state_only.ClearField("payload")
        assert "sim" not in str(state_only).lower().replace(machine.asset_id.lower(), "")

    # The other half of the same coin: asked what it is made of, it says
    # simulated rather than pretending to be steel.
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)
    mirrored = world.store.get_registry(machine.asset_id)
    devices = {d["device"] for d in mirrored["drivers"]}
    assert "simulated" in devices

    # And the machine never claims OFFLINE about itself, which only the
    # server is allowed to conclude.
    statuses = [
        Heartbeat.FromString(p).status
        for t, p in mine_topics
        if t.rsplit("/", 1)[1] == "heartbeat"
    ]
    assert AssetStatus.ASSET_STATUS_OFFLINE not in statuses


# -- criterion 2 -----------------------------------------------------------


async def test_it_carries_out_an_order_from_the_map(client, world, make_machine):
    machine = make_machine(
        a_manifest(
            drivers=a_manifest()["drivers"] + [a_camera_seeing_a_person()],
        )
    )
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    # What its sensor saw became a track, through the public interface.
    await wait_until(lambda: world.store.list_tracks())
    tracks = (await client.get("/v1/tracks")).json()
    assert tracks

    detection = await wait_until(
        lambda: [e for e in world.store.list_events() if "person" in e.text.lower()]
    )
    # The honesty law survives the whole path: driver, core, contract, feed.
    assert "possible" in detection[0].text.lower()
    assert "low confidence" in detection[0].text.lower()

    created = await client.post(
        "/v1/tasks",
        json={
            "asset_id": machine.asset_id,
            "task_type": "navigate",
            "waypoints": [WAYPOINT_NORTH],
            "channel": "map",
        },
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]

    await wait_until(
        lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_DONE, timeout=20
    )

    task = world.store.get_task(task_id)
    states = [change.state for change in task.status_history]
    assert TaskState.TASK_STATE_PENDING in states
    assert TaskState.TASK_STATE_ACCEPTED in states
    assert TaskState.TASK_STATE_RUNNING in states
    assert states[-1] == TaskState.TASK_STATE_DONE

    # It really travelled.
    assert world.store.get_asset(machine.asset_id).position.latitude_deg > SITE_LAT + 0.0004


async def test_an_order_it_cannot_carry_out_is_refused_in_words(client, world, make_machine):
    machine = make_machine(a_manifest())
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    created = await client.post(
        "/v1/tasks",
        json={"asset_id": machine.asset_id, "task_type": "launch_torpedo", "channel": "map"},
    )
    task_id = created.json()["task_id"]

    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_FAILED)
    assert "cannot" in world.store.get_task(task_id).status_history[-1].message.lower()


# -- criterion 3 -----------------------------------------------------------


async def test_the_task_survives_the_link_being_cut(client, world, make_machine):
    """The disconnection law, on a machine that is actually working.

    The link goes down mid-order. The machine keeps driving, keeps seeing,
    and holds what it saw. When the link returns, nothing that mattered was
    lost and the order is still the machine's own.
    """
    machine = make_machine(
        a_manifest(
            max_speed_mps=3.0,
            drivers=a_manifest()["drivers"]
            + [a_camera_seeing_a_person(after_seconds=0.2, repeat_every_seconds=0.2, count=4)],
        )
    )
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    created = await client.post(
        "/v1/tasks",
        json={
            "asset_id": machine.asset_id,
            "task_type": "navigate",
            "waypoints": [WAYPOINT_FAR],
            "channel": "map",
        },
    )
    task_id = created.json()["task_id"]
    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_RUNNING)

    before = world.store.get_asset(machine.asset_id).position.latitude_deg
    observations_before = len(world.store.list_observations())

    machine.comms.drop()

    # Alone, the machine carries on: it is still executing its order, and
    # it is still its own task, not something it abandoned.
    await wait_until(lambda: machine.runtime.core.world.current_task is not None)
    await wait_until(lambda: machine.registry.snapshot()["healthy"])
    await wait_until(lambda: machine.runtime.core.link.held > 0, timeout=10)

    moved = machine.runtime.drivers.locomotion.pose().latitude_deg
    assert moved > before, "the machine stopped driving when it lost the link"
    assert len(world.store.list_observations()) == observations_before, (
        "observations reached the server while the link was down"
    )

    held = machine.runtime.core.link.held
    machine.comms.restore()

    # Everything held arrives, and it arrives as observations rather than
    # as a summary: history is not rewritten.
    await wait_until(
        lambda: len(world.store.list_observations()) >= observations_before + held, timeout=10
    )
    assert machine.runtime.core.link.held == 0


# -- criterion 4 -----------------------------------------------------------


async def test_a_different_manifest_changes_behaviour_with_no_code_change(
    client, world, make_machine
):
    """The HAL law, made testable.

    Two machines, one runtime, one line of Python between them: none. The
    second manifest declares a different speed, a different sensor count,
    and a shorter list of work it will accept, and every one of those
    differences shows up in what the machine does.
    """
    reference = make_machine(
        a_manifest(
            name="Reference",
            max_speed_mps=25.0,
            max_turn_rate_dps=110.0,
            max_accel_mps2=2.5,
            max_decel_mps2=2.5,
            drivers=a_manifest()["drivers"] + [a_camera_seeing_a_person()],
        )
    )
    light = make_machine(
        a_manifest(
            name="Light",
            max_speed_mps=4.0,
            max_turn_rate_dps=200.0,
            max_accel_mps2=4.0,
            max_decel_mps2=5.0,
            supported_task_types=["navigate", "hold"],
            drivers=a_manifest()["drivers"]
            + [a_camera_seeing_a_person()]
            + [a_camera_seeing_a_person(entity_class="vehicle", confidence=0.7)],
        )
    )
    reference.start()
    light.start()

    await wait_until(lambda: world.store.get_asset(reference.asset_id) is not None)
    await wait_until(lambda: world.store.get_asset(light.asset_id) is not None)

    # Different sensor counts, straight from the manifests.
    assert len(reference.runtime.drivers.sensors) == 1
    assert len(light.runtime.drivers.sensors) == 2

    # Different movement constraints, and every one of them is queryable
    # rather than merely held in a Python object: a limit that shapes how
    # the machine moves but cannot be read back is what the registry law
    # exists to prevent.
    assert reference.runtime.manifest.max_speed_mps == 25.0
    assert light.runtime.manifest.max_speed_mps == 4.0

    ref_config = reference.registry.snapshot()["configuration"]
    light_config = light.registry.snapshot()["configuration"]
    assert ref_config["max_turn_rate_dps"] == 110.0
    assert light_config["max_turn_rate_dps"] == 200.0
    assert ref_config["max_decel_mps2"] == 2.5
    assert light_config["max_decel_mps2"] == 5.0

    # The shorter task list is enforced: the same order one accepts, the
    # other refuses, in words.
    patrol = {
        "task_type": "patrol",
        "waypoints": [WAYPOINT_NORTH, {"latitude_deg": SITE_LAT, "longitude_deg": SITE_LON}],
        "channel": "map",
    }
    accepted = await client.post("/v1/tasks", json={"asset_id": reference.asset_id, **patrol})
    refused = await client.post("/v1/tasks", json={"asset_id": light.asset_id, **patrol})

    await wait_until(
        lambda: world.store.get_task(refused.json()["task_id"]).status
        == TaskState.TASK_STATE_FAILED
    )
    assert (
        "cannot"
        in world.store.get_task(refused.json()["task_id"]).status_history[-1].message.lower()
    )
    await wait_until(
        lambda: world.store.get_task(accepted.json()["task_id"]).status
        in (TaskState.TASK_STATE_RUNNING, TaskState.TASK_STATE_DONE)
    )

    # And each machine is known by the name it declared, not one composed
    # from its class.
    listed = {a["asset_id"]: a for a in (await client.get("/v1/assets")).json()}
    assert listed[reference.asset_id]["display_name"] == "Reference"
    assert listed[light.asset_id]["display_name"] == "Light"


# -- criterion 5 -----------------------------------------------------------


async def test_the_registry_is_queryable_and_reaches_the_world_model(client, world, make_machine):
    """The registry law, both ends.

    The machine can say what it is made of, and that answer reaches the
    world model without an administrator typing it in.
    """
    machine = make_machine(
        a_manifest(name="Registry machine", drivers=a_manifest()["drivers"] + [a_camera_seeing_a_person()])
    )
    machine.start()

    # Locally, on the machine itself.
    local = machine.registry.snapshot()
    assert local["registry_version"] == 1
    names = {d["name"] for d in local["drivers"]}
    assert names == {"simulated_locomotion", "direct_comms", "simulated_camera"}
    assert all("version" in d for d in local["drivers"])
    assert {d["identifier"] for d in local["devices"]} >= {"motor-controller-0", "camera-0"}
    assert local["configuration"]["asset_class"] == "ugv"
    await wait_until(lambda: machine.registry.snapshot()["healthy"])

    # And mirrored, through the contract, with no administrator involved.
    await wait_until(lambda: world.store.get_registry(machine.asset_id) is not None, timeout=10)

    # Reading it is an admin matter, though. Driver versions and bus scans
    # are the system internals the waterline law keeps operators away from.
    refused = await client.get(f"/v1/assets/{machine.asset_id}/registry")
    assert refused.status_code == 403

    mirrored = (
        await client.get(
            f"/v1/assets/{machine.asset_id}/registry",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        )
    ).json()
    assert {d["name"] for d in mirrored["drivers"]} == names
    assert mirrored["manifest"]["name"] == "Registry machine"
    assert mirrored["configuration"]["asset_class"] == "ugv"
    assert [d["driver"] for d in mirrored["health"]]

    # The health a driver reports is a sentence a person can read, not a code.
    for entry in mirrored["health"]:
        assert entry["detail"]
        assert entry["detail"][0].isupper() or entry["detail"][0].islower()


async def test_a_machine_that_has_not_reported_a_registry_says_so_plainly(client, world):
    """A machine with no registry is not an error. Older runtimes and
    third-party assets that speak the contract have none."""
    admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    await client.put(
        "/v1/assets/01THIRDPARTY000000000000A1",
        json={"name": "Someone else's robot", "asset_class": "ugv"},
        headers=admin,
    )
    response = await client.get(
        "/v1/assets/01THIRDPARTY000000000000A1/registry", headers=admin
    )
    assert response.status_code == 404
    assert "what it is made of" in response.json()["detail"]


# -- the failure the audit found -------------------------------------------


async def test_a_route_the_navigator_gives_up_on_is_reported_not_left_running(
    client, world, make_machine
):
    """A navigator that gives up must not leave an order running forever.

    Nav2 abandons routes it cannot finish. If the core treats "not arrived"
    and "given up" as the same thing, the task stays RUNNING for as long as
    the machine has power and the operator keeps reading "on the way" about
    a machine that stopped moving. This pins the reporting, using a
    navigator that gives up on command rather than a real Nav2, because the
    behaviour under test is the core's and not Nav2's.
    """

    class GivesUp:
        """A navigator that follows a route and then abandons it."""

        def __init__(self):
            self.failed = False
            self.arrived = False
            self.progress = 0.3
            self.remaining_m = 40.0
            self._steps = 0

        def follow(self, route):
            self._steps = 0
            self.failed = False

        def cancel(self):
            self.failed = False

        def step(self, dt):
            self._steps += 1
            if self._steps > 3:
                self.failed = True

    machine = make_machine(a_manifest(), navigator=GivesUp())
    machine.start()
    await wait_until(lambda: world.store.get_asset(machine.asset_id) is not None)

    created = await client.post(
        "/v1/tasks",
        json={
            "asset_id": machine.asset_id,
            "task_type": "navigate",
            "waypoints": [WAYPOINT_FAR],
            "channel": "map",
        },
    )
    task_id = created.json()["task_id"]

    await wait_until(
        lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_FAILED, timeout=15
    )

    # And the operator is told in words what happened, not left to infer it.
    failure = world.store.get_task(task_id).status_history[-1]
    assert failure.state == TaskState.TASK_STATE_FAILED
    assert failure.message
    assert "could not" in failure.message.lower()

    # The machine is free to take another order rather than stuck on a
    # route it has already abandoned.
    assert machine.runtime.core.world.current_task is None
