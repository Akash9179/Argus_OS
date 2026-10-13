"""ugv-01's locomotion driver, first version: an inhibited shell.

It registers with the HAL, opens the two boards through the controls,
reports identity and health, and refuses to move until a measured
calibration exists in the manifest. Every number that would make it move
today would be invented, so it does not move. goto() and pose() are
unsupported on this body and say so.
"""
from __future__ import annotations

import time

import pytest

from pilot.hal.drivers.ugv01 import protocol as p
from pilot.hal.drivers.ugv01.controls import Ugv01Controls
from pilot.hal.drivers.ugv01.locomotion import (
    NotCalibrated, StaticLocalization, Ugv01Locomotion, Unsupported,
)
from pilot.hal.interfaces import Waypoint
from pilot.hal.loader import available_drivers, build_drivers
from pilot.hal.manifest import load_manifest
from tests.test_ugv01_controls import FakeClock, FakePort, accel_board, drive_board

MANIFEST = "drive/pilot/manifests/ugv-01.yaml"


@pytest.fixture
def rig():
    clock = FakeClock()
    drive = FakePort(drive_board); accel = FakePort(accel_board)
    controls = Ugv01Controls(drive_port=drive, accel_port=accel, now=clock.now,
                             sleep=clock.sleep, poll_hz=0, steer_sense="left_increases")
    manifest = load_manifest(MANIFEST)
    driver = Ugv01Locomotion(manifest=manifest, controls=controls, now=clock.now)
    yield driver, controls, drive, accel, clock
    driver.stop()


def test_the_driver_is_registered_under_its_manifest_name():
    assert "ugv01_locomotion" in available_drivers()
    assert "static_localization" in available_drivers()


def test_start_opens_the_boards_and_reports_identity(rig):
    driver, controls, drive, accel, clock = rig
    driver.start()
    info = driver.info()
    assert info.kind == "locomotion" and info.name == "ugv01_locomotion"
    assert info.settings["drive_firmware"] == "4.1.3"
    assert info.settings["accel_firmware"] == "1.2"
    assert info.settings["calibrated"] == "no"
    assert info.settings["goto"] == "unsupported" and info.settings["pose"] == "unsupported"
    assert driver.health().healthy is True
    assert accel.writes[0] == p.ACCEL_ZERO


def test_moving_is_refused_without_a_measured_calibration(rig):
    driver, controls, drive, accel, clock = rig
    driver.start()
    with pytest.raises(NotCalibrated):
        driver.set_velocity(0.5, 0.0)
    with pytest.raises(NotCalibrated):
        driver.set_velocity(0.0, 10.0)
    assert all(not w.startswith(b"0x05 0[12]") for w in drive.writes)
    assert p.accel_duty(20) not in accel.writes


def test_zero_velocity_is_a_stop_and_is_always_accepted(rig):
    driver, controls, drive, accel, clock = rig
    driver.start()
    drive.writes.clear(); accel.writes.clear()
    driver.set_velocity(0.0, 0.0)
    assert accel.writes[-1] == p.ACCEL_ZERO
    assert p.steer("stop") in drive.writes


def test_stop_moving_sends_zero_and_steering_stop_but_no_brake_yet(rig):
    driver, controls, drive, accel, clock = rig
    driver.start()
    drive.writes.clear(); accel.writes.clear()
    driver.stop_moving()
    assert accel.writes[-1] == p.ACCEL_ZERO
    assert p.steer("stop") in drive.writes
    assert p.brake("apply") not in drive.writes, "the brake stroke is uncharacterised: no service brake in M0"


def test_goto_and_pose_are_unsupported_and_say_so(rig):
    driver, controls, drive, accel, clock = rig
    driver.start()
    with pytest.raises(Unsupported, match="navigator"):
        driver.goto(Waypoint(latitude_deg=23.19, longitude_deg=79.98))
    with pytest.raises(Unsupported, match="odometry"):
        driver.pose()


def test_health_follows_the_controls_faults(rig):
    driver, controls, drive, accel, clock = rig
    driver.start()
    drive.rx.put(b"0x00;WD;TIMEOUT\n")
    deadline = time.time() + 1.0
    while time.time() < deadline and driver.health().healthy:
        time.sleep(0.02)
    h = driver.health()
    assert h.healthy is False
    assert "WD" in h.detail or "stopped" in h.detail.lower()


def test_static_localization_reports_an_unhealthy_fixed_position():
    manifest = load_manifest(MANIFEST)
    loc = StaticLocalization(manifest=manifest, locomotion=None, latitude_deg=23.19, longitude_deg=79.98)
    loc.start()
    est = loc.estimate()
    assert (est.latitude_deg, est.longitude_deg) == (23.19, 79.98)
    assert est.healthy is False and est.source == "none"
    assert est.speed_mps == 0.0 and est.horizontal_uncertainty_m is None


def test_the_manifest_builds_a_driver_set_with_injected_controls():
    clock = FakeClock()
    controls = Ugv01Controls(drive_port=FakePort(drive_board), accel_port=FakePort(accel_board),
                             now=clock.now, sleep=clock.sleep, poll_hz=0)
    manifest = load_manifest(MANIFEST)
    locomotion = Ugv01Locomotion(manifest=manifest, controls=controls, now=clock.now)
    drivers = build_drivers(manifest, locomotion=locomotion)
    assert drivers.locomotion is locomotion
    assert drivers.localization.info().name == "static_localization"
    drivers.locomotion.start()
    snap = drivers.registry.snapshot() if hasattr(drivers, "registry") else None
    drivers.locomotion.stop()
