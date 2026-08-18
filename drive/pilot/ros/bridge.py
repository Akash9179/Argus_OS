"""The bridge between ROS2 and the HAL.

Nav2 plans and controls; it ends up publishing velocity commands and
expecting odometry and a transform back. This node is the only place in the
system that knows that, and it translates in both directions through the
HAL's two seams:

    /cmd_vel  ->  locomotion.set_velocity(linear, angular)
    localization.estimate()  ->  /odom and the odom -> base_link transform

Commands go to the thing that turns wheels; position comes from the
LocalizationProvider (ADR-0004), never from the wheels directly. Given no
provider the bridge builds the dead-reckoning default around the same
locomotion driver, which is bit-for-bit the old behavior; a manifest that
names a better provider changes what Nav2 navigates on with no code
change here.

That direction of dependency matters. Nav2 sits above the HAL and talks to
whatever drivers the manifest named, so choosing Nav2 is not a decision
that reaches the hardware, and swapping the hardware is not a decision
that reaches Nav2.

Coordinates: Nav2 works in a local metric frame, and the contract works in
WGS84. The datum is the machine's pose when this node starts, and the
conversion is a local tangent plane about it. That is accurate well past
the range any single task covers, and it keeps the machine free of a map
server it would otherwise need just to agree where zero is.

Importing this module requires ROS2 and is therefore only done inside the
container. Nothing above the HAL imports it.
"""

from __future__ import annotations

import logging
import math
import threading

from geometry_msgs.msg import Quaternion, TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from tf2_ros import TransformBroadcaster

from pilot import geo
from pilot.hal.interfaces import LocomotionDriver
from pilot.hal.localization import (
    DeadReckoningLocalization,
    LocalizationProvider,
    PoseEstimate,
)

log = logging.getLogger(__name__)


class LocomotionBridge(Node):
    """Wires the HAL's locomotion and localization seams to the ROS2 graph."""

    def __init__(
        self,
        locomotion: LocomotionDriver,
        localization: LocalizationProvider | None = None,
        rate_hz: float = 20.0,
    ):
        super().__init__("argus_locomotion_bridge")
        self._locomotion = locomotion
        self._localization = localization or DeadReckoningLocalization(locomotion)

        estimate = self._localization.estimate()
        self._datum = (estimate.latitude_deg, estimate.longitude_deg)

        self._odom = self.create_publisher(Odometry, "odom", 10)
        self._tf = TransformBroadcaster(self)
        self.create_subscription(Twist, "cmd_vel", self._on_cmd_vel, 10)
        self.create_timer(1.0 / rate_hz, self._publish_state)

        self.get_logger().info(
            f"bridge up, datum {self._datum[0]:.6f} {self._datum[1]:.6f}"
        )

    # -- ROS2 to the machine ------------------------------------------------

    def _on_cmd_vel(self, msg: Twist) -> None:
        # Two conversions, and the second one is easy to miss. ROS works in
        # radians per second about a z axis that is positive anticlockwise;
        # the driver interface works in degrees per second of compass
        # heading, which is positive clockwise. Getting the sign wrong does
        # not fail loudly: the machine steers away from every correction
        # and spins on the spot while the controller fights it.
        self._locomotion.set_velocity(
            linear_mps=msg.linear.x, angular_dps=-math.degrees(msg.angular.z)
        )

    # -- the machine to ROS2 ------------------------------------------------

    def _publish_state(self) -> None:
        tick = getattr(self._locomotion, "tick", None)
        if tick is not None:
            tick()

        estimate = self._localization.estimate()
        x, y = self.to_local(estimate.latitude_deg, estimate.longitude_deg)
        yaw = math.radians(90.0 - estimate.heading_deg)  # compass to ENU
        now = self.get_clock().now().to_msg()

        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_link"
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.orientation = _yaw_to_quaternion(yaw)
        odom.twist.twist.linear.x = estimate.speed_mps
        self._odom.publish(odom)

        transform = TransformStamped()
        transform.header.stamp = now
        transform.header.frame_id = "odom"
        transform.child_frame_id = "base_link"
        transform.transform.translation.x = x
        transform.transform.translation.y = y
        transform.transform.rotation = _yaw_to_quaternion(yaw)
        self._tf.sendTransform(transform)

    # -- position, for the things wired through this bridge ------------------

    def estimate(self) -> PoseEstimate:
        """Where the machine believes it is, from the provider."""
        return self._localization.estimate()

    def local_xy(self) -> tuple[float, float]:
        """The current estimate in the bridge's local metric frame."""
        estimate = self._localization.estimate()
        return self.to_local(estimate.latitude_deg, estimate.longitude_deg)

    # -- coordinates --------------------------------------------------------

    def to_local(self, latitude_deg: float, longitude_deg: float) -> tuple[float, float]:
        """WGS84 to meters east and north of the datum."""
        lat0, lon0 = self._datum
        north = geo.distance_m(lat0, lon0, latitude_deg, lon0)
        east = geo.distance_m(lat0, lon0, lat0, longitude_deg)
        if latitude_deg < lat0:
            north = -north
        if longitude_deg < lon0:
            east = -east
        return east, north

    def to_global(self, x: float, y: float) -> tuple[float, float]:
        """Meters east and north of the datum, back to WGS84."""
        return geo.offset(self._datum[0], self._datum[1], north_m=y, east_m=x)


def _yaw_to_quaternion(yaw: float) -> Quaternion:
    return Quaternion(x=0.0, y=0.0, z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0))


def spin_in_background(node: Node) -> SingleThreadedExecutor:
    """Run a node's callbacks on a thread of their own.

    The bridge has to be publishing before Nav2 can finish coming up: its
    costmaps refuse to activate until base_link resolves against odom. So
    the bridge spins on its own thread from the moment it is created,
    rather than waiting for anything else to be ready.
    """
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    def _spin() -> None:
        try:
            executor.spin()
        except ExternalShutdownException:
            # Normal: rclpy was shut down while this thread was waiting.
            # Letting it surface as an unhandled thread exception makes
            # every clean shutdown look like a fault.
            pass

    threading.Thread(target=_spin, daemon=True).start()
    return executor
