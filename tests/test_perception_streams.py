"""The perception stream seam (ADR-0003).

The old sensor interface could only say "I detected a thing". These tests
prove the richer seam: typed streams beside the old poll(), discoverable
per sensor, carrying non-Detection data (a GNSS fix) across the HAL with
nothing above the HAL learning a device name. The old interface keeps
working through a shim for as long as any driver still speaks it.
"""

from __future__ import annotations

from pilot.hal.interfaces import Detection
from pilot.hal.loader import build_drivers
from pilot.hal.manifest import parse_manifest
from pilot.hal.perception import GnssSample, stream_kinds, streams_of


def manifest_with(drivers: list[dict]) -> object:
    return parse_manifest(
        {
            "asset_id": "TEST-01",
            "asset_class": "ugv",
            "name": "Test machine",
            "max_speed_mps": 2.0,
            "drivers": drivers,
        }
    )


BASE = [
    {"kind": "locomotion", "driver": "simulated_locomotion"},
    {"kind": "comms", "driver": "simulated_comms"},
]


class OldStyleSensor:
    """A driver written against the original poll()-only interface."""

    def info(self):
        from pilot.hal.interfaces import DriverInfo

        return DriverInfo(name="old_style", kind="sensor", version="0", device="test")

    def health(self):
        from pilot.hal.interfaces import DriverHealth

        return DriverHealth(True, "ok")

    def start(self):
        pass

    def stop(self):
        pass

    def poll(self):
        return [
            Detection(entity_class="person", confidence=0.5, offset_north_m=1.0, offset_east_m=0.0)
        ]


def test_an_old_style_driver_is_a_detection_stream_through_the_shim():
    sensor = OldStyleSensor()
    streams = streams_of(sensor)
    assert set(streams) == {"detections"}
    found = streams["detections"].read()
    assert len(found) == 1 and found[0].entity_class == "person"


def test_the_simulated_camera_declares_its_stream():
    manifest = manifest_with(
        BASE
        + [
            {
                "kind": "sensor",
                "driver": "simulated_camera",
                "sightings": [
                    {"after_seconds": 0.0, "entity_class": "person", "confidence": 0.7}
                ],
            }
        ]
    )
    drivers = build_drivers(manifest)
    drivers.start()
    try:
        streams = streams_of(drivers.sensors[0])
        assert "detections" in streams
        assert any(d.entity_class == "person" for d in streams["detections"].read())
    finally:
        drivers.stop()


def test_a_gnss_fix_crosses_the_hal_without_being_a_detection():
    """The acceptance test for the seam itself: data that is not a
    Detection reaches a consumer through the HAL, declared only in the
    manifest. This is what the old interface made impossible."""
    manifest = manifest_with(
        BASE
        + [
            {
                "kind": "sensor",
                "driver": "simulated_gnss",
                "latitude_deg": 12.9716,
                "longitude_deg": 77.5946,
                "horizontal_accuracy_m": 1.2,
            }
        ]
    )
    drivers = build_drivers(manifest)
    drivers.start()
    try:
        streams = streams_of(drivers.sensors[0])
        assert "gnss" in streams and "detections" not in streams
        fixes = streams["gnss"].read()
        assert fixes, "a running GNSS reports fixes"
        fix = fixes[-1]
        assert isinstance(fix, GnssSample)
        assert abs(fix.latitude_deg - 12.9716) < 1e-9
        assert fix.horizontal_accuracy_m == 1.2
        assert fix.fix != "none"
    finally:
        drivers.stop()


def test_a_stopped_gnss_reports_nothing_rather_than_a_stale_fix():
    manifest = manifest_with(
        BASE
        + [{"kind": "sensor", "driver": "simulated_gnss", "latitude_deg": 1.0, "longitude_deg": 2.0}]
    )
    drivers = build_drivers(manifest)
    streams = streams_of(drivers.sensors[0])
    assert streams["gnss"].read() == []


def test_the_registry_answers_which_streams_each_sensor_provides():
    """Law 10: capabilities are discoverable as data, not by reading code."""
    manifest = manifest_with(
        BASE
        + [
            {"kind": "sensor", "driver": "simulated_camera", "sightings": []},
            {"kind": "sensor", "driver": "simulated_gnss", "latitude_deg": 0.0, "longitude_deg": 0.0},
        ]
    )
    drivers = build_drivers(manifest)
    by_name = {entry["name"]: entry for entry in drivers.registry.drivers()}
    assert by_name["simulated_camera"]["streams"] == ["detections"]
    assert by_name["simulated_gnss"]["streams"] == ["gnss"]


def test_stream_kinds_helper_matches_streams():
    assert stream_kinds(OldStyleSensor()) == ["detections"]


def test_a_receiver_without_a_fix_does_not_claim_one():
    """Law 7 at the driver level: the health sentence tracks the fix
    state, so a searching receiver never tells an operator it has a fix."""
    manifest = manifest_with(
        BASE
        + [{"kind": "sensor", "driver": "simulated_gnss", "latitude_deg": 0.0,
            "longitude_deg": 0.0, "fix": "none"}]
    )
    drivers = build_drivers(manifest)
    drivers.start()
    try:
        health = drivers.sensors[0].health()
        assert health.healthy
        assert "no fix" in health.detail
        assert "has a fix" not in health.detail
    finally:
        drivers.stop()


def test_an_unknown_fix_value_is_reported_as_stated_not_judged():
    """fix is open vocabulary: a value this build has never heard of is
    neither claimed as a fix nor denied as one."""
    manifest = manifest_with(
        BASE
        + [{"kind": "sensor", "driver": "simulated_gnss", "latitude_deg": 0.0,
            "longitude_deg": 0.0, "fix": "searching"}]
    )
    drivers = build_drivers(manifest)
    drivers.start()
    try:
        detail = drivers.sensors[0].health().detail
        assert "searching" in detail
        assert "has a fix" not in detail and "no fix" not in detail
    finally:
        drivers.stop()
