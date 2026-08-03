"""Booting one machine.

Read the manifest, build the drivers it names, wire the autonomy core to a
navigator and a LINK client, and start. Everything specific to a machine
has been decided by the time this function returns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from pilot import hal  # noqa: F401  registers the drivers this build carries
from pilot.autonomy.core import AutonomyCore, RuntimeConfig
from pilot.autonomy.navigator import DirectNavigator, Navigator
from pilot.hal.loader import DriverSet, build_drivers
from pilot.hal.manifest import Manifest, load_manifest
from pilot.link_client import LinkClient

log = logging.getLogger(__name__)

DEFAULT_LANGUAGE = Path(__file__).parent / "data" / "runtime_language.yaml"
MANIFEST_DIR = Path(__file__).parent / "manifests"


def load_language(path: str | Path = DEFAULT_LANGUAGE) -> dict[str, str]:
    """The words this machine uses about its own orders."""
    return (yaml.safe_load(Path(path).read_text()) or {}).get("messages", {})


class Runtime:
    """One booted machine, ready to run."""

    def __init__(
        self,
        manifest: Manifest,
        drivers: DriverSet,
        core: AutonomyCore,
        link: LinkClient,
    ):
        self.manifest = manifest
        self.drivers = drivers
        self.core = core
        self.link = link

    def start(self) -> None:
        self.drivers.start()
        self.link.start()

    def run(self, duration_s: float | None = None) -> None:
        self.core.run(duration_s=duration_s)

    def stop(self) -> None:
        self.core.stop()
        self.link.stop()
        self.drivers.stop()

    @property
    def registry(self):
        return self.drivers.registry


def boot(
    manifest_path: str | Path,
    topic_prefix: str = "site",
    navigator: Navigator | None = None,
    language_path: str | Path = DEFAULT_LANGUAGE,
    config: RuntimeConfig | None = None,
    **driver_overrides: Any,
) -> Runtime:
    """Bring one machine up from its manifest."""
    manifest = load_manifest(manifest_path)
    drivers = build_drivers(manifest, **driver_overrides)

    cfg = config or RuntimeConfig(messages=load_language(language_path))
    if not cfg.messages:
        cfg.messages = load_language(language_path)

    holder: dict[str, AutonomyCore] = {}
    link = LinkClient(
        asset_id=manifest.asset_id,
        comms=drivers.comms,
        topic_prefix=topic_prefix,
        on_task=lambda assignment: holder["core"].on_task(assignment),
    )

    core = AutonomyCore(
        manifest=manifest,
        drivers=drivers,
        navigator=navigator or DirectNavigator(drivers.locomotion),
        link=link,
        config=cfg,
    )
    holder["core"] = core

    log.info(
        "%s is up: %s, top speed %s m/s, %d sensors",
        manifest.name,
        manifest.asset_class,
        manifest.max_speed_mps,
        len(drivers.sensors),
    )
    return Runtime(manifest=manifest, drivers=drivers, core=core, link=link)
