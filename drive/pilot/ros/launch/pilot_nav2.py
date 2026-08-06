"""Bringing up Nav2.

Nav2's own navigation_launch brings up the planner, controller, behaviors,
waypoint follower and smoother. One thing is added here that a machine with
a surveyed site would get elsewhere: a static map -> odom transform, because
there is no map server and no localization against a survey. The machine's
odom frame is its datum, so map and odom coincide. Stage 3B replaces this
with the localization source of truth once that decision is made on
hardware.

The runtime itself is deliberately not launched from here. It is an
ordinary process that happens to talk to ROS through the bridge, and on a
real machine it is a service rather than a launch node. Keeping the two
separate means the runtime can be restarted without restarting Nav2, and
means nothing about the runtime depends on ROS2's launch system.

Run with:
    ros2 launch pilot/ros/launch/pilot_nav2.py
"""

from __future__ import annotations

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PILOT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAV2_PARAMS = os.path.join(PILOT_ROOT, "config", "nav2.yaml")


def generate_launch_description() -> LaunchDescription:
    params = LaunchConfiguration("params_file")

    nav2_launch = os.path.join(
        "/opt/ros/humble/share/nav2_bringup/launch", "navigation_launch.py"
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("params_file", default_value=NAV2_PARAMS),
            # map and odom coincide: the datum is wherever the machine
            # booted, and there is no survey to localize against yet.
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="map_to_odom",
                arguments=["0", "0", "0", "0", "0", "0", "map", "odom"],
                output="screen",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_launch),
                launch_arguments={
                    "use_sim_time": "false",
                    "params_file": params,
                    "autostart": "true",
                }.items(),
            ),
        ]
    )
