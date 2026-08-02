"""Configuration for the world model server.

Every tunable lives here and is overridable by environment variable, so no
deployment ever needs a code change. The product name is a single
configurable constant (PRODUCT_NAME) because the name is a placeholder.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The product name is a placeholder. It appears in exactly one place so that
# renaming later costs nothing. It also seeds the default transport topic
# prefix, which is why it must never be hardcoded anywhere else.
PRODUCT_NAME = os.getenv("PRODUCT_NAME", "argus")


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    """Server settings. Frozen: read once at startup, never mutated."""

    # Transport (the reference transport is MQTT; see link/README.md).
    mqtt_host: str = os.getenv("MQTT_HOST", "127.0.0.1")
    mqtt_port: int = _env_int("MQTT_PORT", 1883)
    topic_prefix: str = os.getenv("TOPIC_PREFIX", PRODUCT_NAME)

    # Live state and fan-out.
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    # Durable history.
    db_path: str = os.getenv("DB_PATH", str(REPO_ROOT / "var" / "track.db"))

    # Liveness. Assets heartbeat at 1 Hz by default, so five seconds is five
    # missed heartbeats before the asset is declared offline.
    heartbeat_timeout_s: float = _env_float("HEARTBEAT_TIMEOUT_S", 5.0)
    watchdog_interval_s: float = _env_float("WATCHDOG_INTERVAL_S", 1.0)

    # Track lifecycle.
    track_lost_after_s: float = _env_float("TRACK_LOST_AFTER_S", 15.0)
    track_close_after_s: float = _env_float("TRACK_CLOSE_AFTER_S", 300.0)

    # Fusion gates for the default associator.
    assoc_max_distance_m: float = _env_float("ASSOC_MAX_DISTANCE_M", 40.0)
    assoc_max_age_s: float = _env_float("ASSOC_MAX_AGE_S", 30.0)

    # How long an asset has to acknowledge a task before it is failed.
    task_ack_timeout_s: float = _env_float("TASK_ACK_TIMEOUT_S", 10.0)

    # Operator-facing language and access control, both data files.
    event_templates_path: str = os.getenv(
        "EVENT_TEMPLATES_PATH", str(Path(__file__).parent / "data" / "event_templates.yaml")
    )
    tokens_path: str = os.getenv("TOKENS_PATH", str(REPO_ROOT / "var" / "tokens.yaml"))

    # The contract versions this server speaks.
    link_version: int = 1
    ontology_version: int = 1


settings = Settings()
