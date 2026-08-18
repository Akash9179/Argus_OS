"""Loading a simulated vehicle from a scenario file."""

from __future__ import annotations

from pathlib import Path

import yaml

from sim.vehicle import DEFAULT_TASK_TYPES, ScriptedObservation, VehicleConfig

DEFAULT_SCENARIO = Path(__file__).parent / "scenarios" / "default.yaml"
DEFAULT_LANGUAGE = Path(__file__).parent / "data" / "vehicle_language.yaml"


def load_language(path: str | Path = DEFAULT_LANGUAGE) -> dict[str, str]:
    """The words this machine uses about its own orders."""
    return (yaml.safe_load(Path(path).read_text()) or {}).get("messages", {})


def load(
    path: str | Path = DEFAULT_SCENARIO, language_path: str | Path = DEFAULT_LANGUAGE
) -> VehicleConfig:
    data = yaml.safe_load(Path(path).read_text())

    asset = data["asset"]
    start = data["start"]
    motion = data.get("motion", {})
    battery = data.get("battery", {})

    observations = [
        ScriptedObservation(
            after_seconds=float(o["after_seconds"]),
            entity_class=o["entity_class"],
            confidence=float(o["confidence"]),
            offset_north_m=float(o.get("offset_north_m", 0.0)),
            offset_east_m=float(o.get("offset_east_m", 0.0)),
            narration=o.get("narration", ""),
            attributes={str(k): str(v) for k, v in (o.get("attributes") or {}).items()},
            repeat_every_seconds=float(o.get("repeat_every_seconds", 0.0)),
            count=int(o.get("count", 1)),
        )
        for o in data.get("observations", [])
    ]

    capabilities = dict(asset.get("capabilities", {}))
    # What the vehicle can do is scenario data, declared inside its
    # capabilities where the rest of its self-description lives. A list
    # or the manifest's comma-joined form both work; the comma form is
    # what goes on the wire either way (link/CONVENTIONS.md).
    declared_types = capabilities.pop("supported_task_types", None)
    if declared_types is None:
        supported = DEFAULT_TASK_TYPES
    elif isinstance(declared_types, str):
        supported = tuple(t.strip() for t in declared_types.split(",") if t.strip())
    else:
        supported = tuple(str(t) for t in declared_types)

    return VehicleConfig(
        asset_id=asset["asset_id"],
        asset_class=asset["asset_class"],
        name=asset.get("name", ""),
        capabilities=capabilities,
        supported_task_types=supported,
        start_latitude_deg=float(start["latitude_deg"]),
        start_longitude_deg=float(start["longitude_deg"]),
        speed_mps=float(motion.get("speed_mps", 2.5)),
        heartbeat_hz=float(motion.get("heartbeat_hz", 1.0)),
        telemetry_hz=float(motion.get("telemetry_hz", 5.0)),
        battery_start=float(battery.get("start", 0.92)),
        battery_drain_per_minute=float(battery.get("drain_per_minute", 0.004)),
        observations=observations,
        messages=load_language(language_path),
    )
