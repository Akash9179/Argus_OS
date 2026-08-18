"""Nav2 as a navigator.

The autonomy core asks a navigator to follow a route and to say how far
along it is. `DirectNavigator` answers that itself; this one hands the route
to Nav2 and reports what Nav2 says. The core cannot tell the difference,
which is the point: choosing a planner is a configuration decision, not an
architecture one.

Nav2 reaches the machine only through the locomotion driver, via the bridge
in pilot/ros/bridge.py. Nothing in this file touches hardware, and nothing
in it knows what the machine is.

Importing this module requires ROS2, so it happens only inside the
container. The core imports the Navigator protocol, never this file.
"""

from __future__ import annotations

import logging
import math

from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

from pilot.hal.interfaces import Waypoint
from pilot.hal.manifest import Manifest
from pilot.ros.bridge import LocomotionBridge

log = logging.getLogger(__name__)


class Nav2Navigator:
    """Follows a route by handing it to Nav2's waypoint follower."""

    def __init__(self, bridge: LocomotionBridge, navigator: BasicNavigator | None = None):
        self._bridge = bridge
        self._nav = navigator or BasicNavigator()
        self._route: list[Waypoint] = []
        self._total_m = 0.0
        self._remaining_m = 0.0
        self._active = False
        self._arrived = False
        self._failed = False

    def apply_manifest(self, manifest: Manifest, timeout_s: float = 10.0) -> dict[str, bool]:
        """Push the booted machine's own numbers into Nav2.

        Nav2's parameter file has to contain something, and whatever it
        contains describes some machine. Leaving those values operative
        would put one body's top speed and footprint above the hardware
        abstraction layer, so they are overwritten here from the manifest
        that actually booted.

        Returns which parameters were accepted, so a machine can report
        honestly that it is navigating on defaults rather than on its own
        constraints. Nav2 not being up yet is not fatal: navigating a large
        machine with a small machine's footprint is worth a warning, not a
        refusal to move.
        """
        radius = _footprint_radius(manifest)
        # Every number below comes from the manifest. None of them may be a
        # literal describing some particular body: a yaw limit written here
        # is one machine's yaw limit imposed on every machine.
        turn_rate_rps = math.radians(manifest.max_turn_rate_dps)
        wanted: dict[str, list[tuple[str, object]]] = {
            "/controller_server": [
                ("FollowPath.vx_max", manifest.max_speed_mps),
                ("FollowPath.wz_max", turn_rate_rps),
                ("FollowPath.ax_max", manifest.max_accel_mps2),
                ("FollowPath.ax_min", -manifest.max_decel_mps2),
                ("FollowPath.az_max", turn_rate_rps * 2.0),
                ("FollowPath.AckermannConstraints.min_turning_r", manifest.min_turn_radius_m or 0.0),
            ],
            # Both the footprint and the cushion around it scale with the
            # body. A large machine keeping a small machine's clearance is
            # a large machine that clips things.
            "/local_costmap/local_costmap": [
                ("robot_radius", radius),
                ("inflation_layer.inflation_radius", radius * 1.25),
            ],
            "/global_costmap/global_costmap": [
                ("robot_radius", radius),
                ("inflation_layer.inflation_radius", radius * 1.25),
            ],
            "/velocity_smoother": [
                ("max_velocity", [manifest.max_speed_mps, 0.0, turn_rate_rps]),
                ("min_velocity", [0.0, 0.0, -turn_rate_rps]),
                ("max_accel", [manifest.max_accel_mps2, 0.0, turn_rate_rps * 2.0]),
                ("max_decel", [-manifest.max_decel_mps2, 0.0, -turn_rate_rps * 2.0]),
            ],
        }
        if manifest.min_turn_radius_m:
            # A machine that cannot turn in place is not a differential
            # machine, whatever the default said.
            wanted["/controller_server"].append(("FollowPath.motion_model", "Ackermann"))

        applied: dict[str, bool] = {}
        for node, parameters in wanted.items():
            for name, value in parameters:
                applied[f"{node}:{name}"] = self._set_parameter(node, name, value, timeout_s)

        missed = [key for key, ok in applied.items() if not ok]
        if missed:
            log.warning(
                "nav2 kept its default values for %d parameters, so this machine is "
                "navigating on numbers that are not its own: %s",
                len(missed),
                ", ".join(missed),
            )
        return applied

    def _set_parameter(self, node: str, name: str, value: object, timeout_s: float) -> bool:
        """Set one parameter on one Nav2 node.

        On its own short-lived node rather than on BasicNavigator's, which
        is already being spun by its own machinery: spinning it again from
        here deadlocks or drops the response.
        """
        import rclpy
        from rcl_interfaces.srv import SetParameters
        from rclpy.node import Node
        from rclpy.parameter import Parameter

        caller = Node(f"argus_param_setter_{abs(hash((node, name))) % 100000}")
        client = caller.create_client(SetParameters, f"{node}/set_parameters")
        try:
            if not client.wait_for_service(timeout_sec=timeout_s):
                return False
            request = SetParameters.Request()
            request.parameters = [Parameter(name, value=value).to_parameter_msg()]
            future = client.call_async(request)
            rclpy.spin_until_future_complete(caller, future, timeout_sec=timeout_s)
            result = future.result()
            return bool(result and result.results and all(r.successful for r in result.results))
        except Exception as exc:  # a parameter Nav2 does not have is not fatal
            log.warning("could not set %s on %s: %s", name, node, exc)
            return False
        finally:
            caller.destroy_node()

    def wait_until_ready(self, timeout_s: float = 90.0) -> None:
        """Block until Nav2 has come up. Called once at boot.

        Bounded on purpose. Nav2's own wait blocks forever, and the failure
        it hides is a common one: the costmaps cannot activate until the
        bridge is publishing a transform, so a machine whose locomotion
        driver never started waits silently rather than saying what is
        wrong. A machine that cannot navigate should say so and let the
        operator see it, which is what raising here allows.
        """
        import threading

        done = threading.Event()

        def _wait() -> None:
            self._nav.waitUntilNav2Active(localizer="controller_server")
            done.set()

        threading.Thread(target=_wait, daemon=True).start()
        if not done.wait(timeout_s):
            raise TimeoutError(
                f"nav2 did not become active within {timeout_s:.0f}s. "
                "Its costmaps need the locomotion bridge publishing "
                "base_link against odom before they will activate."
            )

    # -- the Navigator protocol --------------------------------------------

    def follow(self, route: list[Waypoint]) -> None:
        self._route = list(route)
        self._arrived = False
        self._failed = False
        if not self._route:
            self._active = False
            return

        poses = [self._to_pose(w) for w in self._route]
        self._total_m = self._length(self._route)
        self._remaining_m = self._total_m
        self._nav.followWaypoints(poses)
        self._active = True

    def cancel(self) -> None:
        if self._active:
            self._nav.cancelTask()
        self._active = False
        self._route = []

    def step(self, dt: float) -> None:
        if not self._active:
            return
        if not self._nav.isTaskComplete():
            feedback = self._nav.getFeedback()
            if feedback is not None and self._route:
                # The waypoint follower reports which waypoint it is on, so
                # remaining distance is what is left of the route from there.
                index = getattr(feedback, "current_waypoint", 0)
                self._remaining_m = self._length(self._route[index:])
            return

        result = self._nav.getResult()
        self._active = False
        if result == TaskResult.SUCCEEDED:
            self._remaining_m = 0.0
            self._arrived = True
            self._failed = False
            return
        # A route Nav2 could not finish is not an arrival, and it is not
        # silence either. The core reads `failed` and tells the operator
        # the order stopped, in words.
        log.warning("nav2 did not finish the route: %s", result)
        self._arrived = False
        self._failed = True

    @property
    def arrived(self) -> bool:
        return self._arrived

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def progress(self) -> float:
        if self._total_m <= 0:
            return 1.0
        travelled = self._total_m - self._remaining_m
        return max(0.0, min(1.0, travelled / self._total_m))

    @property
    def remaining_m(self) -> float:
        return self._remaining_m

    # -- coordinates --------------------------------------------------------

    def _to_pose(self, waypoint: Waypoint) -> PoseStamped:
        x, y = self._bridge.to_local(waypoint.latitude_deg, waypoint.longitude_deg)
        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = self._nav.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.w = 1.0
        return pose

    def _length(self, route: list[Waypoint]) -> float:
        if not route:
            return 0.0
        x, y = self._bridge.local_xy()
        total = 0.0
        for waypoint in route:
            wx, wy = self._bridge.to_local(waypoint.latitude_deg, waypoint.longitude_deg)
            total += math.hypot(wx - x, wy - y)
            x, y = wx, wy
        return total


def _footprint_radius(manifest: Manifest) -> float:
    """A circle that contains the machine.

    Nav2 wants either a radius or a polygon. A manifest that declares its
    dimensions gets a circle around its longest half-diagonal; one that
    declares nothing gets a metre, which is small enough to be wrong and
    large enough to be noticed rather than a value that silently pretends
    to be a measurement.
    """
    length = manifest.length_m
    width = manifest.width_m
    if length is None or width is None:
        return 1.0
    return math.hypot(length, width) / 2.0
