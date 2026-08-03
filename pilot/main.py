"""Run one machine.

    python -m pilot.main --manifest pilot/manifests/ugv-reference.yaml

The local registry interface is served alongside, so an admin surface or a
future setup copilot can ask what this machine is made of without anyone
opening a terminal on it. The registry law says that has to be structured
data; this is where it is served.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from pilot.runtime import MANIFEST_DIR, Runtime, boot

log = logging.getLogger("pilot")

DEFAULT_MANIFEST = MANIFEST_DIR / "ugv-reference.yaml"


def registry_server(runtime: Runtime, port: int) -> HTTPServer:
    """The machine's own registry interface, served locally.

    Read-only and unauthenticated by design: it is reachable only on the
    machine itself, and everything it returns is also mirrored upward
    through the contract. It exists so the answer to "what is in this
    machine" never requires reading code.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server's spelling
            routes = {
                "/registry": runtime.registry.snapshot,
                "/registry/drivers": runtime.registry.drivers,
                "/registry/devices": runtime.registry.devices,
                "/registry/health": runtime.registry.health,
                "/registry/configuration": runtime.registry.configuration,
            }
            handler = routes.get(self.path)
            if handler is None:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(handler(), indent=2, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            return

    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def build_nav2_navigator(runtime):
    """Wire Nav2 to the locomotion driver.

    Imported here rather than at module scope because it needs ROS2, which
    exists only inside the container. A machine running the direct
    navigator has no ROS2 and must still boot.
    """
    import rclpy

    from pilot.autonomy.nav2 import Nav2Navigator
    from pilot.ros.bridge import LocomotionBridge, spin_in_background

    rclpy.init()
    # The bridge starts publishing immediately: Nav2's costmaps will not
    # activate until they can resolve base_link against odom, so the
    # machine has to be talking before Nav2 can finish coming up.
    bridge = LocomotionBridge(runtime.drivers.locomotion)
    spin_in_background(bridge)

    navigator = Nav2Navigator(bridge)
    log.info("waiting for nav2 to come up")
    navigator.wait_until_ready()

    # Say what actually happened, not what was intended. apply_manifest
    # returns which constraints Nav2 accepted precisely so this line cannot
    # claim the machine is running on its own numbers when it is not.
    applied = navigator.apply_manifest(runtime.manifest)
    missed = [key for key, ok in applied.items() if not ok]
    if missed:
        log.warning(
            "nav2 is up, but %d of %s's constraints were refused, so it is "
            "navigating partly on values that are not its own",
            len(missed),
            runtime.manifest.name,
        )
    else:
        log.info("nav2 is up, running on %s's own constraints", runtime.manifest.name)
    return navigator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one machine.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--prefix", default="site", help="LINK topic prefix")
    parser.add_argument("--registry-port", type=int, default=8200)
    parser.add_argument("--duration", type=float, default=None, help="Stop after N seconds.")
    parser.add_argument(
        "--navigator",
        choices=("direct", "nav2"),
        default="direct",
        help="Who plans the route. Nav2 needs ROS2 and the nav2 stack running.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s %(message)s"
    )

    if args.navigator == "nav2":
        # The drivers have to exist before the bridge can be wired to them,
        # so the machine is booted once with no navigator and given one.
        runtime = boot(args.manifest, topic_prefix=args.prefix)
        runtime.core.navigator = build_nav2_navigator(runtime)
    else:
        runtime = boot(args.manifest, topic_prefix=args.prefix)
    server = registry_server(runtime, args.registry_port)
    runtime.start()

    def shutdown(*_args) -> None:
        log.info("stopping")
        runtime.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("registry on http://127.0.0.1:%d/registry", args.registry_port)
    try:
        runtime.run(duration_s=args.duration)
    finally:
        runtime.stop()
        server.shutdown()


if __name__ == "__main__":
    main()
