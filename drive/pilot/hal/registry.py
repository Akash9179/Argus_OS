"""The HAL registry.

The registry law: everything the HAL knows must be queryable structured
data, not just code. Installed drivers and their versions, the manifest the
machine booted on, what the buses report, the configuration actually in
force, and each driver's health.

Two consumers, one of which does not exist yet. Today it is served locally
on the machine and mirrored into the world model's asset record, which is
how an admin surface can answer "what is this machine made of" without
anyone opening a terminal. Later a setup copilot reads the same structure,
which is why it is data rather than log lines.

The snapshot is a plain dictionary on purpose. It crosses into the world
model as the contract's open `Struct`, so anything a newer driver reports
survives an older server.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from pilot.hal.interfaces import Driver, DriverHealth
from pilot.hal.language import say
from pilot.hal.manifest import Manifest

REGISTRY_VERSION = 1


@dataclass(frozen=True)
class Device:
    """Something found on a bus.

    In Stage 3A the simulated drivers declare what they present. In 3B the
    real drivers report what an actual scan found, and the shape here does
    not change, which is the point of writing it down now.
    """

    bus: str  # for example "gmsl2", "usb", "can", "simulated"
    identifier: str
    description: str
    present: bool


class DeviceScanner(Protocol):
    """A driver that can say what hardware it found."""

    def scan(self) -> list[Device]: ...


class Registry:
    """What this machine is made of, as data."""

    def __init__(self, manifest: Manifest):
        self._manifest = manifest
        self._drivers: list[Driver] = []
        self._booted_at = time.time()

    def register(self, driver: Driver) -> None:
        self._drivers.append(driver)

    # -- queries -----------------------------------------------------------

    def drivers(self) -> list[dict[str, Any]]:
        entries = []
        for driver in self._drivers:
            info = driver.info()
            entries.append(
                {
                    "name": info.name,
                    "kind": info.kind,
                    "version": info.version,
                    "device": info.device,
                    "settings": dict(info.settings),
                }
            )
        return entries

    def health(self) -> list[dict[str, Any]]:
        entries = []
        for driver in self._drivers:
            info = driver.info()
            try:
                state: DriverHealth = driver.health()
            except Exception as exc:  # a driver that cannot answer is not healthy
                entries.append(
                    {
                        "driver": info.name,
                        "healthy": False,
                        "detail": say("no_answer", reason=exc),
                    }
                )
                continue
            entries.append(
                {"driver": info.name, "healthy": state.healthy, "detail": state.detail}
            )
        return entries

    def devices(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for driver in self._drivers:
            scan = getattr(driver, "scan", None)
            if scan is None:
                continue
            for device in scan():
                found.append(
                    {
                        "bus": device.bus,
                        "identifier": device.identifier,
                        "description": device.description,
                        "present": device.present,
                        "driver": driver.info().name,
                    }
                )
        return found

    def configuration(self) -> dict[str, Any]:
        """The settings actually in force, which is not always what the
        manifest asked for: a driver may clamp a value it cannot honour."""
        return {
            "asset_id": self._manifest.asset_id,
            "asset_class": self._manifest.asset_class,
            # Every constraint that steers the planner is queryable here.
            # A limit that shapes how the machine moves but cannot be read
            # back is exactly what the registry law exists to prevent.
            "max_speed_mps": self._manifest.max_speed_mps,
            "max_turn_rate_dps": self._manifest.max_turn_rate_dps,
            "max_accel_mps2": self._manifest.max_accel_mps2,
            "max_decel_mps2": self._manifest.max_decel_mps2,
            "min_turn_radius_m": self._manifest.min_turn_radius_m,
            "supported_task_types": list(self._manifest.supported_task_types),
            "drivers_requested": [
                {"kind": spec.kind, "driver": spec.driver, "settings": dict(spec.settings)}
                for spec in self._manifest.drivers
            ],
        }

    def healthy(self) -> bool:
        return all(entry["healthy"] for entry in self.health())

    def snapshot(self) -> dict[str, Any]:
        """Everything, in one structure, for the local interface and the
        mirror into the world model."""
        return {
            "registry_version": REGISTRY_VERSION,
            "booted_at": self._booted_at,
            "manifest": self._manifest.to_capabilities(),
            "configuration": self.configuration(),
            "drivers": self.drivers(),
            "devices": self.devices(),
            "health": self.health(),
            "healthy": self.healthy(),
        }
