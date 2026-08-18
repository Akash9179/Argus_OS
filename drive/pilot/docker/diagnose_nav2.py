"""Watch what Nav2 and the locomotion driver are actually doing.

Not a test. A thing to run when the machine is not arriving and the
question is which half of the seam is at fault.
"""

from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

from pilot import geo
from pilot.autonomy.nav2 import Nav2Navigator
from pilot.hal.drivers.simulated import SimulatedLocomotion
from pilot.hal.interfaces import Waypoint
from pilot.hal.manifest import parse_manifest
from pilot.ros.bridge import LocomotionBridge, spin_in_background

SITE_LAT, SITE_LON = 51.50450, -0.12000
GOAL_LAT, GOAL_LON = SITE_LAT + 0.00036, SITE_LON


def main() -> None:
    rclpy.init()
    manifest = parse_manifest(
        {
            "asset_id": "01PILOT000000000000DIAG1",
            "asset_class": "ugv",
            "name": "Diagnostic",
            "max_speed_mps": 4.0,
            "drivers": [
                {"kind": "locomotion", "driver": "simulated_locomotion"},
                {"kind": "comms", "driver": "simulated_comms"},
            ],
        }
    )
    locomotion = SimulatedLocomotion(
        manifest, start_latitude_deg=SITE_LAT, start_longitude_deg=SITE_LON
    )
    locomotion.start()

    bridge = LocomotionBridge(locomotion, rate_hz=30.0)
    spin_in_background(bridge)

    # Listen to what Nav2 is commanding, so we can tell "never commanded"
    # apart from "commanded and went nowhere".
    watcher = Node("cmd_vel_watcher")
    heard: list[Twist] = []
    watcher.create_subscription(Twist, "cmd_vel", heard.append, 10)
    spin_in_background(watcher)

    navigator = Nav2Navigator(bridge)
    print("waiting for nav2")
    navigator.wait_until_ready()
    print("nav2 active")

    goal_x, goal_y = bridge.to_local(GOAL_LAT, GOAL_LON)
    print(f"goal in local frame: x={goal_x:.1f} y={goal_y:.1f}")

    navigator.follow([Waypoint(GOAL_LAT, GOAL_LON)])

    for second in range(60):
        time.sleep(1.0)
        navigator.step(1.0)
        pose = bridge.estimate()
        x, y = bridge.to_local(pose.latitude_deg, pose.longitude_deg)
        remaining = geo.distance_m(pose.latitude_deg, pose.longitude_deg, GOAL_LAT, GOAL_LON)
        last = heard[-1] if heard else None
        print(
            f"{second:3d}s  x={x:7.2f} y={y:7.2f} hdg={pose.heading_deg:6.1f} "
            f"speed={pose.speed_mps:5.2f}  remaining={remaining:6.1f}m  "
            f"cmds={len(heard)} last_v={last.linear.x if last else 0:5.2f} "
            f"last_w={last.angular.z if last else 0:5.2f}  arrived={navigator.arrived}"
        )
        if navigator.arrived:
            print("arrived")
            break

    rclpy.shutdown()


if __name__ == "__main__":
    main()
