"""Localization as a first-class provider (ADR-0004).

"Where am I" stops being the motor controller's answer. These tests prove:
a machine that declares no localization gets an honest dead-reckoning
provider wrapped around its locomotion (behavior unchanged); a manifest can
swap the provider with no code change; and the autonomy core reads position
only from the provider, so a better answer changes what the machine reports
without touching the core.
"""

from __future__ import annotations

from pilot.hal.interfaces import DriverHealth, DriverInfo, Pose
from pilot.hal.loader import build_drivers, register_driver
from pilot.hal.localization import DeadReckoningLocalization, PoseEstimate
from pilot.hal.manifest import parse_manifest


def manifest_with(drivers: list[dict]) -> object:
    return parse_manifest(
        {
            "asset_id": "TEST-02",
            "asset_class": "ugv",
            "name": "Test machine",
            "max_speed_mps": 2.0,
            "drivers": drivers,
        }
    )


BASE = [
    {"kind": "locomotion", "driver": "simulated_locomotion", "start_latitude_deg": 10.0, "start_longitude_deg": 20.0},
    {"kind": "comms", "driver": "simulated_comms"},
]


def test_a_machine_that_declares_no_localization_gets_dead_reckoning():
    drivers = build_drivers(manifest_with(BASE))
    assert isinstance(drivers.localization, DeadReckoningLocalization)
    drivers.start()
    try:
        estimate = drivers.localization.estimate()
        assert isinstance(estimate, PoseEstimate)
        assert estimate.latitude_deg == 10.0
        assert estimate.longitude_deg == 20.0
        assert estimate.source == "dead_reckoning"
        # Honesty: dead reckoning does not know its own error, and must
        # not invent a number for it.
        assert estimate.horizontal_uncertainty_m is None
    finally:
        drivers.stop()


def test_the_provider_is_in_the_registry_like_any_other_driver():
    drivers = build_drivers(manifest_with(BASE))
    kinds = {entry["kind"] for entry in drivers.registry.drivers()}
    assert "localization" in kinds


class PinnedLocalization:
    """A provider that answers from somewhere the wheels never went."""

    def __init__(self, manifest=None, **_ignored):
        self._running = False

    def info(self):
        return DriverInfo(name="pinned_localization", kind="localization", version="0", device="test")

    def health(self):
        return DriverHealth(self._running, "pinned")

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def estimate(self) -> PoseEstimate:
        return PoseEstimate(
            latitude_deg=51.5,
            longitude_deg=-0.1,
            heading_deg=90.0,
            speed_mps=0.0,
            source="pinned",
            horizontal_uncertainty_m=0.5,
        )


register_driver("pinned_localization", PinnedLocalization)


def test_a_manifest_cannot_smuggle_a_locomotion_instance_into_settings():
    """"locomotion" is a reserved settings key: the runtime injects the
    real driver there, and YAML must not be able to replace it."""
    import pytest

    from pilot.hal.loader import DriverNotAvailable

    manifest = manifest_with(
        BASE + [{"kind": "localization", "driver": "pinned_localization", "locomotion": "bogus"}]
    )
    with pytest.raises(DriverNotAvailable):
        build_drivers(manifest)


def test_a_manifest_swaps_the_provider_with_no_code_change():
    manifest = manifest_with(BASE + [{"kind": "localization", "driver": "pinned_localization"}])
    drivers = build_drivers(manifest)
    drivers.start()
    try:
        estimate = drivers.localization.estimate()
        assert estimate.source == "pinned"
        assert estimate.latitude_deg == 51.5
        # The wheels still believe they are at the start position; the
        # provider's answer wins wherever position is consumed.
        assert drivers.locomotion.pose().latitude_deg == 10.0
    finally:
        drivers.stop()


def test_the_core_reports_the_providers_position_not_the_wheels(monkeypatch):
    """The seam proof at the top: telemetry and observations come from the
    localization provider, so replacing dead reckoning with GNSS or VSLAM
    changes what the machine says without a core change."""
    from pilot.autonomy.core import AutonomyCore, RuntimeConfig
    from pilot.autonomy.navigator import DirectNavigator
    from pilot.link_client import LinkClient

    manifest = manifest_with(
        BASE
        + [
            {"kind": "localization", "driver": "pinned_localization"},
            {
                "kind": "sensor",
                "driver": "simulated_camera",
                "sightings": [
                    {"after_seconds": 0.0, "entity_class": "person", "confidence": 0.7,
                     "offset_north_m": 0.0, "offset_east_m": 0.0}
                ],
            },
        ]
    )
    drivers = build_drivers(manifest)

    sent = {"telemetry": [], "observations": []}

    class RecordingLink:
        def offer_registry(self, snapshot):
            pass

        def heartbeat(self, **kwargs):
            pass

        def telemetry(self, position, heading_deg, speed_mps, **kwargs):
            sent["telemetry"].append(position)

        def observation(self, observation):
            sent["observations"].append(observation)

        def task_status(self, **kwargs):
            pass

    core = AutonomyCore(
        manifest=manifest,
        drivers=drivers,
        navigator=DirectNavigator(drivers.locomotion, localization=drivers.localization),
        link=RecordingLink(),
        config=RuntimeConfig(messages={}),
    )
    drivers.start()
    try:
        core.run(duration_s=0.3)
    finally:
        core.stop()
        drivers.stop()

    assert sent["telemetry"], "the core sent telemetry"
    assert abs(sent["telemetry"][-1].latitude_deg - 51.5) < 1e-9
    assert sent["observations"], "the sighting became an observation"
    # The detection had zero offset, so its world position is exactly the
    # provider's answer, not the wheels' start position.
    assert abs(sent["observations"][0].position.latitude_deg - 51.5) < 1e-9
