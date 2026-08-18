"""Turning a manifest into a running set of drivers.

The manifest names drivers; this file maps those names to implementations
and builds them with the settings the manifest gave. It is the whole of
what "adapts at boot with no code change" means in practice.

A manifest naming a driver this build does not have is refused at boot with
a sentence saying which one, rather than starting up half-equipped. A
half-equipped machine that drives is the failure mode worth designing
against.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from pilot.hal.interfaces import CommsDriver, Driver, LocomotionDriver, SensorDriver
from pilot.hal.localization import DeadReckoningLocalization, LocalizationProvider
from pilot.hal.manifest import Manifest
from pilot.hal.registry import Registry

log = logging.getLogger(__name__)

# name -> factory. Real drivers register here in Stage 3B alongside the
# simulated ones; nothing above this file changes when they do.
_FACTORIES: dict[str, Callable[..., Driver]] = {}


class DriverNotAvailable(RuntimeError):
    """The manifest asked for a driver this build does not carry."""


def register_driver(name: str, factory: Callable[..., Driver]) -> None:
    _FACTORIES[name] = factory


def available_drivers() -> list[str]:
    return sorted(_FACTORIES)


class DriverSet:
    """The drivers one machine booted with."""

    def __init__(
        self,
        locomotion: LocomotionDriver,
        comms: CommsDriver,
        sensors: list[SensorDriver],
        registry: Registry,
        localization: LocalizationProvider,
    ):
        self.locomotion = locomotion
        self.comms = comms
        self.sensors = sensors
        self.registry = registry
        self.localization = localization

    def start(self) -> None:
        self.locomotion.start()
        self.localization.start()
        for sensor in self.sensors:
            sensor.start()
        self.comms.start()

    def stop(self) -> None:
        for sensor in self.sensors:
            sensor.stop()
        self.localization.stop()
        self.locomotion.stop()
        self.comms.stop()


def build_drivers(manifest: Manifest, **overrides: Any) -> DriverSet:
    """Build every driver the manifest names.

    `overrides` lets a caller inject an already-constructed driver by kind,
    which is how a test wires a machine straight to a server and how the
    containerized runtime hands in a comms driver it made itself. It is not
    a way to skip the manifest: a kind the manifest never declared is still
    an error.
    """
    locomotion_spec = manifest.driver_for("locomotion")
    comms_spec = manifest.driver_for("comms")
    if locomotion_spec is None:
        raise DriverNotAvailable(f"{manifest.name} declares no locomotion driver")
    if comms_spec is None:
        raise DriverNotAvailable(f"{manifest.name} declares no comms driver")

    locomotion = overrides.get("locomotion") or _build(locomotion_spec.driver, manifest, locomotion_spec.settings)
    comms = overrides.get("comms") or _build(comms_spec.driver, manifest, comms_spec.settings)

    sensors: list[SensorDriver] = list(overrides.get("sensors") or [])
    if not sensors:
        for spec in manifest.sensors():
            sensors.append(_build(spec.driver, manifest, spec.settings))

    # Localization is the fourth driver kind (ADR-0004). A manifest that
    # declares one gets it; a manifest that declares nothing gets honest
    # dead reckoning wrapped around its own locomotion, which is exactly
    # the behavior every machine had before the seam existed. Declared
    # factories receive the locomotion driver too, because providers that
    # fuse wheel odometry need it and the ones that do not ignore it.
    localization = overrides.get("localization")
    if localization is None:
        localization_spec = manifest.driver_for("localization")
        if localization_spec is None:
            localization = DeadReckoningLocalization(locomotion)
        else:
            # "locomotion" is a reserved settings key: it carries the
            # injected driver instance, and a manifest that names it would
            # silently replace real hardware with whatever YAML said.
            if "locomotion" in localization_spec.settings:
                raise DriverNotAvailable(
                    f"{manifest.name}'s localization driver settings use the reserved key "
                    "'locomotion', which the runtime supplies itself"
                )
            localization = _build(
                localization_spec.driver,
                manifest,
                {"locomotion": locomotion, **localization_spec.settings},
            )

    registry = Registry(manifest)
    registry.register(locomotion)
    registry.register(localization)
    registry.register(comms)
    for sensor in sensors:
        registry.register(sensor)

    log.info(
        "%s booted with %d drivers: %s",
        manifest.name,
        len(registry.drivers()),
        ", ".join(entry["name"] for entry in registry.drivers()),
    )
    return DriverSet(
        locomotion=locomotion,
        comms=comms,
        sensors=sensors,
        registry=registry,
        localization=localization,
    )


def _build(name: str, manifest: Manifest, settings: dict[str, Any]) -> Any:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise DriverNotAvailable(
            f"this build has no driver called {name!r}. It carries: {', '.join(available_drivers())}"
        )
    return factory(manifest=manifest, **settings)
