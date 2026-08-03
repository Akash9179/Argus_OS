"""A route through Nav2, end to end inside the container.

This is the one that answers criterion 2's "through Nav2": an order arrives
as a contract message, the autonomy core plans it, Nav2 produces a path and
controls along it, and the machine's locomotion driver is what moves. If
any link in that chain is fictional this test does not pass.

It needs Nav2 already running in the same ROS graph, which the runner
script starts. Skipped rather than failed when Nav2 is absent, so that the
bridge tests remain runnable on their own.
"""

from __future__ import annotations

import time

import pytest
import rclpy
from link.v1.messages_pb2 import TaskAssignment
from link.v1.ontology_pb2 import Position, Task, TaskParameters, TaskState

from pilot import geo
from pilot.autonomy.core import AutonomyCore, RuntimeConfig
from pilot.hal.drivers.simulated import SimulatedComms, SimulatedLocomotion
from pilot.hal.loader import build_drivers
from pilot.hal.manifest import parse_manifest
from pilot.link_client import LinkClient
from pilot.runtime import load_language

SITE_LAT = 51.50450
SITE_LON = -0.12000

# 40 meters north. Far enough to need a plan, near enough to finish fast.
GOAL_LAT = SITE_LAT + 0.00036
GOAL_LON = SITE_LON


def a_manifest() -> dict:
    return {
        "asset_id": "01PILOT0000000000000NAV21",
        "asset_class": "ugv",
        "name": "Nav2 test machine",
        "max_speed_mps": 4.0,
        "drivers": [
            {"kind": "locomotion", "driver": "simulated_locomotion"},
            {"kind": "comms", "driver": "simulated_comms"},
        ],
    }


@pytest.fixture(scope="module")
def machine(ros):
    from pilot.autonomy.nav2 import Nav2Navigator
    from pilot.ros.bridge import LocomotionBridge, spin_in_background

    manifest = parse_manifest(a_manifest())
    locomotion = SimulatedLocomotion(
        manifest, start_latitude_deg=SITE_LAT, start_longitude_deg=SITE_LON
    )
    comms = SimulatedComms(manifest)
    drivers = build_drivers(manifest, locomotion=locomotion, comms=comms, sensors=[])
    drivers.start()

    bridge = LocomotionBridge(locomotion, rate_hz=30.0)
    spin_in_background(bridge)

    navigator = Nav2Navigator(bridge)
    try:
        navigator.wait_until_ready()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"nav2 is not running in this ROS graph: {exc}")

    # Nav2 runs on this machine's numbers, not on whatever the params file
    # happened to contain. Named individually rather than counted: "some of
    # them landed" passes while the ones that matter are still defaults.
    applied = navigator.apply_manifest(manifest)
    must_land = [
        "/controller_server:FollowPath.vx_max",
        "/controller_server:FollowPath.wz_max",
        "/local_costmap/local_costmap:robot_radius",
        "/global_costmap/global_costmap:robot_radius",
        "/velocity_smoother:max_velocity",
    ]
    refused = [key for key in must_land if not applied.get(key)]
    assert not refused, f"nav2 kept its own values for {refused}"

    holder: dict = {}
    link = LinkClient(
        asset_id=manifest.asset_id,
        comms=comms,
        topic_prefix="test",
        on_task=lambda a: holder["core"].on_task(a),
    )
    core = AutonomyCore(
        manifest=manifest,
        drivers=drivers,
        navigator=navigator,
        link=link,
        config=RuntimeConfig(messages=load_language(), tick_s=0.02),
    )
    holder["core"] = core
    link.start()

    yield core, locomotion

    core.stop()
    drivers.stop()


def test_nav2_drives_the_machine_to_the_goal(machine):
    core, locomotion = machine
    import threading

    thread = threading.Thread(target=core.run, daemon=True)
    thread.start()

    task = Task(
        task_id="01TASK000000000000000NAV2",
        asset_id=core.manifest.asset_id,
        task_type="navigate",
        parameters=TaskParameters(
            waypoints=[Position(latitude_deg=GOAL_LAT, longitude_deg=GOAL_LON)]
        ),
        status=TaskState.TASK_STATE_PENDING,
    )
    core.on_task(TaskAssignment(link_version=1, ontology_version=1, task=task))

    # It accepted the order and started working on it.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and core.world.current_task is None:
        time.sleep(0.1)
    assert core.world.current_task is not None, "the order was never accepted"

    # Nav2 planned and controlled: the locomotion driver was actually driven.
    moved = False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if locomotion.pose().speed_mps > 0.0:
            moved = True
            break
        time.sleep(0.1)
    assert moved, "nav2 never commanded the locomotion driver"

    # And it got there.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and core.world.current_task is not None:
        time.sleep(0.2)

    pose = locomotion.pose()
    remaining = geo.distance_m(pose.latitude_deg, pose.longitude_deg, GOAL_LAT, GOAL_LON)
    assert core.world.current_task is None, "the order never finished"
    assert remaining < 5.0, f"stopped {remaining:.1f} m from the goal"

    core.stop()
    thread.join(timeout=5)
