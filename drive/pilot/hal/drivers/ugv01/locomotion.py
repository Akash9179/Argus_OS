"""ugv-01's locomotion driver, behind the HAL. First version: an inhibited shell.

What it does today: registers with the loader as `ugv01_locomotion`,
opens the two boards through Ugv01Controls (the single owner of both
ports), reports identity and health to the registry, accepts a stop,
and refuses to move. It refuses because every number that would turn
"go at this speed" into a throttle duty or a steering angle is still
unmeasured: speed per duty, the sensor-to-road-wheel mapping, the
wheelbase. The bench on 13 Oct 2026 measured directions, rates and end
stops, not those. When the first ground session fills a `calibration`
block in the manifest, set_velocity() gets its mapping and this
docstring changes. Until then a movement command raises NotCalibrated,
which the registry shows as "movement held".

What it does not do, by design:
- goto(): this body does its own point-to-point movement no better than
  a navigator producing velocity commands would, so goto() raises
  Unsupported. A manifest for this body pairs it with the ROS bridge and
  Nav2, or with a navigator that calls set_velocity().
- pose(): there is no odometry source on the vehicle (no wheel encoder,
  no speed sensor). pose() raises Unsupported, and the manifest declares
  `static_localization`, which reports the configured site position as
  unmeasured and unhealthy, so the runtime boots honestly.
- a service brake: the brake stroke is uncharacterised (force, holding),
  so stop_moving() is throttle zero and steering stop. The controls'
  own safe stop keeps the same policy (brake_on_stop off).

Command expiry: set_velocity() is the heartbeat the controls want. The
supervision thread only ticks the controls; it never renews command
authority. A command older than COMMAND_EXPIRY_S while motion is
commanded makes the driver stop and latch; clear() is the deliberate
recovery, for a human decision above.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable

from pilot.hal.drivers.ugv01.controls import Refused, Ugv01Controls
from pilot.hal.drivers.ugv01.link import PySerialPort
from pilot.hal.interfaces import DriverHealth, DriverInfo, Pose, Waypoint
from pilot.hal.language import say
from pilot.hal.loader import register_driver
from pilot.hal.localization import PoseEstimate
from pilot.hal.registry import Device

DRIVER_VERSION = "0.1.0"
COMMAND_EXPIRY_S = 0.3
TICK_HZ = 20.0


class NotCalibrated(RuntimeError):
    """A movement was asked of a driver whose manifest carries no measured calibration."""


class Unsupported(RuntimeError):
    """This body does not provide the primitive; the message says what to use instead."""


class Ugv01Locomotion:
    def __init__(
        self,
        manifest: Any = None,
        *,
        drive_port: str | None = None,
        accel_port: str | None = None,
        steer_sense: str | None = None,
        max_duty: int = 30,
        calibration: dict | None = None,
        controls: Ugv01Controls | None = None,
        now: Callable[[], float] = time.monotonic,
        **_ignored: Any,
    ) -> None:
        self._manifest = manifest
        self._now = now
        self._calibration = calibration or None
        if controls is None:
            if not drive_port or not accel_port:
                raise ValueError("ugv01_locomotion needs drive_port and accel_port in the manifest")
            controls = Ugv01Controls(
                drive_port=PySerialPort(drive_port), accel_port=PySerialPort(accel_port),
                steer_sense=steer_sense, max_duty=max_duty, brake_on_stop=False,
            )
        self._c = controls
        self._ports = (drive_port or "injected", accel_port or "injected")
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_command_at: float | None = None
        self._motion_commanded = False
        self._latched_reason: str | None = None

    # ------------------------------------------------------------- identity

    def info(self) -> DriverInfo:
        snap = self._c.snapshot()
        return DriverInfo(
            name="ugv01_locomotion",
            kind="locomotion",
            version=DRIVER_VERSION,
            device="ugv-01 drive module and throttle board",
            settings={
                "drive_port": str(self._ports[0]),
                "accel_port": str(self._ports[1]),
                "drive_firmware": str(snap["drive"]["firmware"] or "unknown"),
                "accel_firmware": str(snap["accel"]["firmware"] or "unknown"),
                "calibrated": "yes" if self._calibration else "no",
                "goto": "unsupported",
                "pose": "unsupported",
                "service_brake": "not yet",
            },
        )

    def health(self) -> DriverHealth:
        if not self._running:
            return DriverHealth(False, say("ugv01_not_started"))
        snap = self._c.snapshot()
        if snap["faults"]:
            return DriverHealth(False, say("ugv01_faulted", reason="; ".join(snap["faults"])))
        if self._latched_reason:
            return DriverHealth(False, say("ugv01_stopped", reason=self._latched_reason))
        if snap["safe_stopped"]:
            return DriverHealth(False, say("ugv01_stopped", reason="safe stop"))
        if not self._calibration:
            return DriverHealth(True, say("ugv01_ready_inhibited"))
        return DriverHealth(True, say("ugv01_ready"))

    def scan(self) -> list[Device]:
        snap = self._c.snapshot()
        return [
            Device(bus="serial", identifier=str(self._ports[0]),
                   description="ARGUS DRIVE module (steering, brake, gear, lights, horn)",
                   present=bool(snap["drive"]["connected"])),
            Device(bus="serial", identifier=str(self._ports[1]),
                   description="throttle board",
                   present=bool(snap["accel"]["connected"])),
        ]

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
        self._c.start()                       # identity and state only; nothing moves
        with self._lock:
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._supervise, daemon=True,
                                            name="ugv01-locomotion")
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            running = self._running
            self._running = False
        self._stop_event.set()
        if running:
            self._c.close()                   # stops first, then lets go of the ports

    def _supervise(self) -> None:
        period = 1.0 / TICK_HZ
        while not self._stop_event.is_set():
            self._c.tick()                    # supervision only; never a heartbeat
            with self._lock:
                last = self._last_command_at
                motion = self._motion_commanded
                latched = self._latched_reason
            if motion and not latched and (last is None or self._now() - last > COMMAND_EXPIRY_S):
                self._halt("command expired")
            time.sleep(period)

    def _halt(self, reason: str) -> None:
        with self._lock:
            self._latched_reason = reason
            self._motion_commanded = False
        self._c.safe_stop(brake=False)

    def clear(self) -> None:
        """A deliberate recovery from above, after a human decision."""
        with self._lock:
            self._latched_reason = None
        self._c.clear_faults()

    # ------------------------------------------------------------- movement

    def set_velocity(self, linear_mps: float, angular_dps: float) -> None:
        if not (math.isfinite(linear_mps) and math.isfinite(angular_dps)):
            raise ValueError("velocity must be finite")
        if abs(linear_mps) < 1e-6 and abs(angular_dps) < 1e-6:
            self.stop_moving()
            return
        if not self._calibration:
            raise NotCalibrated(
                "ugv-01 has no measured calibration (speed per duty, steering mapping, wheelbase); "
                "movement is held until the manifest carries one")
        if self._latched_reason:
            raise Refused("movement refused: %s; clear() first" % self._latched_reason)
        # The calibrated mapping lands with the first ground session; nothing
        # is invented here in the meantime.
        raise NotCalibrated("calibrated movement is not implemented yet")

    def goto(self, waypoint: Waypoint) -> None:
        raise Unsupported("ugv-01 has no point-to-point movement of its own; use a navigator "
                          "that produces velocity commands (the ROS bridge with Nav2)")

    def stop_moving(self) -> None:
        with self._lock:
            self._motion_commanded = False
            self._last_command_at = self._now()
        self._c.heartbeat()
        self._c.set_throttle(0)
        try:
            self._c.steer("stop")
        except Refused:
            pass

    def pose(self) -> Pose:
        raise Unsupported("ugv-01 has no odometry source (no wheel encoder, no speed sensor); "
                          "the manifest declares static_localization until a GNSS is fitted")


class StaticLocalization:
    """A fixed, unmeasured position for a body with no position source.

    Reports the configured site position with healthy False and source
    "none", so the runtime boots and every consumer can see that the
    position is not a reading. Replaced by GNSS fusion in M3.
    """

    def __init__(self, manifest: Any = None, locomotion: Any = None, *,
                 latitude_deg: float = 0.0, longitude_deg: float = 0.0,
                 heading_deg: float = 0.0, **_ignored: Any) -> None:
        self._lat = float(latitude_deg)
        self._lon = float(longitude_deg)
        self._heading = float(heading_deg)
        self._running = False

    def info(self) -> DriverInfo:
        return DriverInfo(name="static_localization", kind="localization", version=DRIVER_VERSION,
                          device="none", settings={"latitude_deg": str(self._lat),
                                                   "longitude_deg": str(self._lon), "measured": "no"})

    def health(self) -> DriverHealth:
        return DriverHealth(False, say("localization_static"))

    def scan(self) -> list[Device]:
        return []

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def estimate(self) -> PoseEstimate:
        return PoseEstimate(
            latitude_deg=self._lat, longitude_deg=self._lon, heading_deg=self._heading,
            speed_mps=0.0, altitude_m=None, horizontal_uncertainty_m=None,
            source="none", healthy=False,
        )


register_driver("ugv01_locomotion", Ugv01Locomotion)
register_driver("static_localization", StaticLocalization)
