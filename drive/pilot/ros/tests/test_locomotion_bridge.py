"""The bridge, against a real ROS2 graph.

These run inside the container, because they need ROS2. They are separate
from the suite that guards every commit for that reason, and they are not a
substitute for it: what they prove is that the seam between Nav2 and the
locomotion driver is real, not that the runtime works.

    docker compose -f pilot/docker/compose.yaml run --rm ros-tests

Nothing here imports the world model or the simulated vehicle.
"""

from __future__ import annotations

import math
import time

import pytest
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node

from pilot.hal.drivers.simulated import SimulatedLocomotion
from pilot.hal.manifest import parse_manifest
from pilot.ros.bridge import LocomotionBridge, spin_in_background

SITE_LAT = 51.50450
SITE_LON = -0.12000


def a_manifest() -> dict:
    return {
        "asset_id": "01PILOT0000000000000TEST1",
        "asset_class": "ugv",
        "name": "Bridge test machine",
        "max_speed_mps": 4.0,
        "drivers": [
            {"kind": "locomotion", "driver": "simulated_locomotion"},
            {"kind": "comms", "driver": "simulated_comms"},
        ],
    }


@pytest.fixture
def bridge(ros):
    manifest = parse_manifest(a_manifest())
    locomotion = SimulatedLocomotion(
        manifest, start_latitude_deg=SITE_LAT, start_longitude_deg=SITE_LON
    )
    locomotion.start()
    node = LocomotionBridge(locomotion, rate_hz=50.0)
    executor = spin_in_background(node)
    yield node, locomotion
    executor.shutdown()
    node.destroy_node()
    locomotion.stop()


def test_a_velocity_command_reaches_the_locomotion_driver(bridge):
    """Nav2's half of the seam: /cmd_vel becomes set_velocity."""
    node, locomotion = bridge

    talker = Node("test_cmd_vel_talker")
    publisher = talker.create_publisher(Twist, "cmd_vel", 10)

    command = Twist()
    command.linear.x = 2.0
    command.angular.z = math.radians(30.0)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        publisher.publish(command)
        rclpy.spin_once(talker, timeout_sec=0.05)
        if locomotion.pose().speed_mps > 0:
            break

    pose = locomotion.pose()
    assert pose.speed_mps == pytest.approx(2.0, abs=0.01), "the command never reached the driver"

    # And the machine actually moved, which means the driver was driven
    # rather than merely told.
    start = (pose.latitude_deg, pose.longitude_deg)
    time.sleep(0.5)
    moved = locomotion.pose()
    assert (moved.latitude_deg, moved.longitude_deg) != start

    talker.destroy_node()


def test_the_driver_pose_reaches_ros_as_odometry(bridge):
    """The machine's half of the seam: pose() becomes /odom and a transform."""
    node, locomotion = bridge

    listener = Node("test_odom_listener")
    heard: list[Odometry] = []
    listener.create_subscription(Odometry, "odom", heard.append, 10)

    locomotion.set_velocity(linear_mps=1.5, angular_dps=0.0)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and len(heard) < 5:
        rclpy.spin_once(listener, timeout_sec=0.05)

    assert len(heard) >= 5, "the bridge never published odometry"
    assert heard[-1].header.frame_id == "odom"
    assert heard[-1].child_frame_id == "base_link"
    assert heard[-1].twist.twist.linear.x == pytest.approx(1.5, abs=0.01)

    # The position it reports is the position the driver believes, expressed
    # in meters from the datum rather than in degrees.
    x = heard[-1].pose.pose.position.x
    y = heard[-1].pose.pose.position.y
    assert abs(x) < 1000 and abs(y) < 1000

    listener.destroy_node()


def test_local_and_global_coordinates_round_trip(bridge):
    """A waypoint converted for Nav2 and back is the same waypoint.

    Worth pinning down: everything above the HAL speaks WGS84 and Nav2
    speaks meters, so this conversion sits between the contract and the
    planner. An error here would look like a machine driving to the wrong
    place for reasons no log would explain.
    """
    node, _ = bridge

    for north_m, east_m in ((0.0, 0.0), (250.0, -120.0), (-40.0, 900.0)):
        lat, lon = node.to_global(east_m, north_m)
        x, y = node.to_local(lat, lon)
        assert x == pytest.approx(east_m, abs=0.5)
        assert y == pytest.approx(north_m, abs=0.5)


def test_odometry_comes_from_the_provider_not_the_wheels(ros):
    """ADR-0004 at this seam: what Nav2 navigates on is the localization
    provider's estimate. A provider that disagrees with the wheels wins,
    which is the whole point of having one."""
    from pilot.hal.localization import PoseEstimate

    manifest = parse_manifest(a_manifest())
    locomotion = SimulatedLocomotion(
        manifest, start_latitude_deg=SITE_LAT, start_longitude_deg=SITE_LON
    )
    locomotion.start()

    class SomewhereElse:
        """A provider that plainly disagrees with the wheel arithmetic."""

        def estimate(self) -> PoseEstimate:
            return PoseEstimate(
                latitude_deg=SITE_LAT + 0.001,
                longitude_deg=SITE_LON,
                heading_deg=90.0,
                speed_mps=1.5,
                source="test_fixture",
            )

    node = LocomotionBridge(locomotion, localization=SomewhereElse(), rate_hz=50.0)
    executor = spin_in_background(node)
    try:
        listener = Node("test_odom_listener")
        heard: list[Odometry] = []
        listener.create_subscription(Odometry, "odom", heard.append, 10)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not heard:
            rclpy.spin_once(listener, timeout_sec=0.05)
        assert heard, "no odometry arrived"

        # The datum is the provider's first estimate, so the provider's
        # own position reads as the origin; the wheels sit ~111m south of
        # it and must NOT be what odometry reports.
        odom = heard[-1]
        assert abs(odom.pose.pose.position.x) < 1.0
        assert abs(odom.pose.pose.position.y) < 1.0
        assert abs(odom.twist.twist.linear.x - 1.5) < 1e-6
        wheels_x, wheels_y = node.to_local(SITE_LAT, SITE_LON)
        assert abs(wheels_y) > 100.0, "the wheel position should be far from the datum"
        listener.destroy_node()
    finally:
        executor.shutdown()
        node.destroy_node()
        locomotion.stop()
