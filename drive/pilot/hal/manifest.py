"""The capability manifest.

One YAML file per machine. It says what the machine is, what it is made of,
and which drivers to load. The runtime reads it at boot and adapts; porting
to a new machine is writing one of these plus any drivers it names.

This file is the reason there is no `if asset_class == "ugv"` anywhere above
the HAL. Anything the autonomy core would otherwise want to branch on is a
field here instead.

Nothing in the manifest is required to be known. A machine that cannot say
what its turning radius is omits the field, and the absence means "not
declared", never zero. Unknown keys are preserved rather than dropped, for
the same reason the contract's open vocabularies are preserved: a manifest
written for a newer runtime must still load on an older one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DriverSpec:
    """A driver the manifest asks the runtime to load."""

    kind: str  # "locomotion", "sensor", or "comms"
    driver: str  # the registered driver name, for example "simulated_locomotion"
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Manifest:
    """What one machine is.

    `extras` holds every key the runtime did not recognise, so a manifest
    written against a later version of this file still loads and still
    reaches the registry intact.
    """

    asset_id: str
    asset_class: str
    name: str

    max_speed_mps: float

    # How fast it can change heading, degrees per second, and how hard it
    # can change speed. A planner that does not know these will command
    # manoeuvres the machine cannot perform and then correct for the
    # machine not performing them.
    #
    # The defaults are deliberately cautious rather than typical: a slow
    # turn and a gentle stop, which no real machine would choose and which
    # every real machine can manage. A default that described some
    # plausible vehicle would be one body's numbers imposed on every
    # machine that forgot to declare its own, and it would drive well
    # enough that nobody noticed. Declare these in the manifest.
    max_turn_rate_dps: float = 30.0
    max_accel_mps2: float = 0.5
    max_decel_mps2: float = 0.5
    # Absent means the machine has not declared one. Ground vehicles that
    # can turn in place declare 0.0, which is a real value and different
    # from not declaring.
    min_turn_radius_m: float | None = None
    can_hover: bool = False

    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None

    battery_capacity_wh: float | None = None
    battery_start_fraction: float = 1.0
    battery_drain_per_minute: float = 0.0

    # What kinds of work this machine will accept. Anything not listed is
    # refused in words rather than dropped, which the contract requires.
    supported_task_types: tuple[str, ...] = ("navigate", "patrol", "hold", "return_home")

    drivers: tuple[DriverSpec, ...] = ()

    extras: dict[str, Any] = field(default_factory=dict)

    def driver_for(self, kind: str) -> DriverSpec | None:
        for spec in self.drivers:
            if spec.kind == kind:
                return spec
        return None

    def sensors(self) -> tuple[DriverSpec, ...]:
        return tuple(spec for spec in self.drivers if spec.kind == "sensor")

    def to_capabilities(self) -> dict[str, Any]:
        """The manifest as the contract's open `Asset.capabilities` struct.

        This is what TRACK mirrors, and it is why C2 can show a machine's
        name without composing one: the name is declared here, by the
        machine, and travels up as data.
        """
        capabilities: dict[str, Any] = {
            "name": self.name,
            "max_speed_mps": self.max_speed_mps,
            "max_turn_rate_dps": self.max_turn_rate_dps,
            "max_accel_mps2": self.max_accel_mps2,
            "max_decel_mps2": self.max_decel_mps2,
            "can_hover": self.can_hover,
        }
        optional = {
            "min_turn_radius_m": self.min_turn_radius_m,
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "battery_capacity_wh": self.battery_capacity_wh,
        }
        capabilities.update({k: v for k, v in optional.items() if v is not None})

        sensors = [spec.driver for spec in self.sensors()]
        if sensors:
            capabilities["sensors"] = ", ".join(sensors)
        capabilities["supported_task_types"] = ", ".join(self.supported_task_types)
        # Anything the manifest declared that this runtime did not know about
        # still reaches the world model rather than being silently lost.
        capabilities.update(self.extras)
        return capabilities


# Keys the loader consumes itself, so everything else falls through to extras.
_KNOWN_TOP_LEVEL = {
    "asset_id",
    "asset_class",
    "name",
    "max_speed_mps",
    "max_turn_rate_dps",
    "max_accel_mps2",
    "max_decel_mps2",
    "min_turn_radius_m",
    "can_hover",
    "dimensions",
    "battery",
    "supported_task_types",
    "drivers",
}


class ManifestError(ValueError):
    """A manifest that cannot be trusted. Refused loudly at boot.

    A machine that boots on a manifest it half-understood is worse than a
    machine that refuses to boot, because the first one drives.
    """


def load_manifest(path: str | Path) -> Manifest:
    """Read one machine's manifest, or refuse to boot."""
    text = Path(path).read_text()
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path} is not readable YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path} does not describe a machine")
    return parse_manifest(raw, source=str(path))


def parse_manifest(raw: dict[str, Any], source: str = "<memory>") -> Manifest:
    for required in ("asset_id", "asset_class", "name", "max_speed_mps"):
        if required not in raw:
            raise ManifestError(f"{source} does not say {required}")

    dimensions = raw.get("dimensions") or {}
    battery = raw.get("battery") or {}

    drivers: list[DriverSpec] = []
    for entry in raw.get("drivers") or []:
        if not isinstance(entry, dict) or "kind" not in entry or "driver" not in entry:
            raise ManifestError(f"{source} has a driver entry without a kind and a driver")
        settings = {k: v for k, v in entry.items() if k not in ("kind", "driver")}
        drivers.append(
            DriverSpec(kind=str(entry["kind"]), driver=str(entry["driver"]), settings=settings)
        )

    task_types = raw.get("supported_task_types")
    if task_types is None:
        supported = Manifest.supported_task_types
    else:
        supported = tuple(str(t) for t in task_types)

    extras = {k: v for k, v in raw.items() if k not in _KNOWN_TOP_LEVEL}

    return Manifest(
        asset_id=str(raw["asset_id"]),
        asset_class=str(raw["asset_class"]),
        name=str(raw["name"]),
        max_speed_mps=float(raw["max_speed_mps"]),
        max_turn_rate_dps=float(raw.get("max_turn_rate_dps", Manifest.max_turn_rate_dps)),
        max_accel_mps2=float(raw.get("max_accel_mps2", Manifest.max_accel_mps2)),
        max_decel_mps2=float(raw.get("max_decel_mps2", Manifest.max_decel_mps2)),
        min_turn_radius_m=_optional_float(raw.get("min_turn_radius_m")),
        can_hover=bool(raw.get("can_hover", False)),
        length_m=_optional_float(dimensions.get("length_m")),
        width_m=_optional_float(dimensions.get("width_m")),
        height_m=_optional_float(dimensions.get("height_m")),
        battery_capacity_wh=_optional_float(battery.get("capacity_wh")),
        battery_start_fraction=float(battery.get("start_fraction", 1.0)),
        battery_drain_per_minute=float(battery.get("drain_per_minute", 0.0)),
        supported_task_types=supported,
        drivers=tuple(drivers),
        extras=extras,
    )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
