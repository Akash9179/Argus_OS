"""The hardware abstraction layer.

Importing this package registers every driver this build carries. Stage 3A
carries the simulated set; Stage 3B adds the real ones next to them without
changing anything above.
"""

from pilot.hal.interfaces import (
    CommsDriver,
    Detection,
    Driver,
    DriverHealth,
    DriverInfo,
    LocomotionDriver,
    Pose,
    SensorDriver,
    Waypoint,
)
from pilot.hal.loader import DriverNotAvailable, DriverSet, build_drivers, register_driver
from pilot.hal.manifest import Manifest, ManifestError, load_manifest, parse_manifest
from pilot.hal.registry import Device, Registry

# Registering the drivers this build carries. The import has the side effect
# on purpose: a driver that is present but unregistered is invisible to the
# manifest, which would make "no code change" untrue.
from pilot.hal.drivers import simulated as _simulated  # noqa: E402,F401  isort:skip

__all__ = [
    "CommsDriver",
    "Detection",
    "Device",
    "Driver",
    "DriverHealth",
    "DriverInfo",
    "DriverNotAvailable",
    "DriverSet",
    "LocomotionDriver",
    "Manifest",
    "ManifestError",
    "Pose",
    "Registry",
    "SensorDriver",
    "Waypoint",
    "build_drivers",
    "load_manifest",
    "parse_manifest",
    "register_driver",
]
