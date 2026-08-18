"""The reboot acceptance test from ARCHITECTURE.md section 8, as a test.

Law 15 says a reboot must not be amnesia: identity, home, configuration,
and the machine's own memory survive a process restart. It also says the
opposite about motion: a machine never automatically resumes physical
motion just because a task was RUNNING before the reboot.

Both halves are tested here against the real runtime, killed mid-task and
booted again over the same local store, exactly the way a power cycle in
the field would do it.
"""

from __future__ import annotations

import asyncio

from link.v1.ontology_pb2 import AssetStatus, TaskState

from tests.conftest import SITE_LAT, SITE_LON, a_manifest, wait_until

# Far enough that the machine is still driving when the process dies.
WAYPOINT_FAR = {"latitude_deg": SITE_LAT + 0.02, "longitude_deg": SITE_LON}

# Where the machine wakes up after the reboot. Deliberately not where it
# started: if home still reads as the original start afterwards, it was
# recovered from the store rather than recomputed from the same inputs.
ELSEWHERE_LAT = SITE_LAT + 0.003


def _woke_up_elsewhere(manifest: dict) -> dict:
    moved = dict(manifest)
    moved["drivers"] = [dict(d) for d in manifest["drivers"]]
    for driver in moved["drivers"]:
        if driver["kind"] == "locomotion":
            driver["start_latitude_deg"] = ELSEWHERE_LAT
    return moved


async def test_a_reboot_is_not_amnesia_and_never_resumes_motion(
    client, world, make_machine, tmp_path
):
    state = tmp_path / "argus_local.db"
    manifest = a_manifest()

    first = make_machine(manifest, state_path=state)
    first.start()
    await wait_until(lambda: world.store.get_asset(first.asset_id) is not None)

    created = await client.post(
        "/v1/tasks",
        json={
            "asset_id": first.asset_id,
            "task_type": "navigate",
            "waypoints": [WAYPOINT_FAR],
            "channel": "map",
        },
    )
    task_id = created.json()["task_id"]
    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_RUNNING)

    # The process dies while the machine is genuinely moving.
    await wait_until(lambda: first.runtime.drivers.localization.estimate().speed_mps > 0)
    home_before = first.runtime.core.world.home
    assert home_before is not None
    first.stop()

    second = make_machine(_woke_up_elsewhere(manifest), state_path=state)
    second.start()
    await wait_until(lambda: second.runtime.core.world.home is not None)

    # Identity and home survived the reboot. Home is where the machine
    # first started, not where it woke up, which proves it came from the
    # store and not from asking the localization provider again.
    assert second.asset_id == first.asset_id
    assert second.runtime.core.world.home == home_before

    # The unfinished order was evaluated and reported, never resumed. The
    # operator is told in words what happened to it.
    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_FAILED)
    message = world.store.get_task(task_id).status_history[-1].message.lower()
    assert "restarted" in message

    # And the wheels never turned: no motion command without a fresh order.
    await asyncio.sleep(0.3)
    estimate = second.runtime.drivers.localization.estimate()
    assert estimate.speed_mps == 0.0
    assert estimate.latitude_deg == ELSEWHERE_LAT
    assert second.runtime.core.status == AssetStatus.ASSET_STATUS_STANDBY
    assert second.runtime.core.world.current_task is None


async def test_a_task_that_commands_no_motion_resumes(client, world, make_machine, tmp_path):
    """Hold is the counter-case: resuming it moves nothing, so it resumes.

    The law forbids resuming physical motion, not remembering orders. A
    machine told to hold position that reboots is still holding position.
    """
    state = tmp_path / "argus_local.db"
    manifest = a_manifest()

    first = make_machine(manifest, state_path=state)
    first.start()
    await wait_until(lambda: world.store.get_asset(first.asset_id) is not None)

    created = await client.post(
        "/v1/tasks",
        json={"asset_id": first.asset_id, "task_type": "hold", "channel": "map"},
    )
    task_id = created.json()["task_id"]
    await wait_until(lambda: world.store.get_task(task_id).status == TaskState.TASK_STATE_RUNNING)
    first.stop()

    second = make_machine(manifest, state_path=state)
    second.start()

    await wait_until(lambda: second.runtime.core.world.current_task is not None)
    assert second.runtime.core.world.current_task.task_id == task_id
    await wait_until(
        lambda: second.runtime.core.status == AssetStatus.ASSET_STATUS_ACTIVE
    )
    assert second.runtime.drivers.localization.estimate().speed_mps == 0.0


async def test_what_the_machine_saw_survives_the_reboot(make_machine, world, tmp_path):
    """The machine's own entity memory is in the store, not the process."""
    from pilot.autonomy.local_world import LocalStore
    from pilot.autonomy.worldslice import WorldSlice
    from pilot.hal.interfaces import Detection

    path = tmp_path / "argus_local.db"

    store = LocalStore(path)
    slice_one = WorldSlice(store=store)
    seen = slice_one.resolve(
        Detection(
            entity_class="person", confidence=0.7, offset_north_m=0.0, offset_east_m=0.0
        ),
        SITE_LAT,
        SITE_LON,
    )
    slice_one.home = (SITE_LAT, SITE_LON)
    store.close()

    reopened = LocalStore(path)
    slice_two = WorldSlice(store=reopened)
    assert seen.entity_id in slice_two.entities
    assert slice_two.entities[seen.entity_id].entity_class == "person"
    assert slice_two.home == (SITE_LAT, SITE_LON)
    reopened.close()


async def test_the_journal_is_append_only_and_ordered(tmp_path):
    """Decisions and transitions land in the journal, in order, forever.

    The journal has no update and no delete; that absence is the feature.
    Sync and learning read it through cursors (ADR-0005), so a rewritten
    past would be a lie told to every consumer downstream.
    """
    from pilot.autonomy.local_world import LocalStore

    store = LocalStore(tmp_path / "argus_local.db")
    store.append("boot", asset_id="ugv-test", boot_count=1)
    store.append("home_set", latitude_deg=SITE_LAT, longitude_deg=SITE_LON)
    store.append("task_accepted", task_id="t-1", task_type="navigate")

    entries = store.journal()
    assert [e.kind for e in entries] == ["boot", "home_set", "task_accepted"]
    assert [e.seq for e in entries] == sorted(e.seq for e in entries)
    assert entries[0].detail["asset_id"] == "ugv-test"
    assert all(e.ts > 0 for e in entries)
    assert not hasattr(store, "delete_journal")
    store.close()


async def test_boots_are_counted_and_identity_recorded(tmp_path):
    from pilot.autonomy.local_world import LocalStore

    path = tmp_path / "argus_local.db"

    store = LocalStore(path)
    assert store.record_boot("ugv-7", "Seventh machine", "ugv") == 1
    store.close()

    again = LocalStore(path)
    assert again.record_boot("ugv-7", "Seventh machine", "ugv") == 2
    identity = again.identity()
    assert identity is not None
    assert identity["asset_id"] == "ugv-7"
    assert identity["name"] == "Seventh machine"
    again.close()
