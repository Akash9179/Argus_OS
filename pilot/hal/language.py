"""The words drivers use about themselves.

Loaded once from `pilot/data/driver_language.yaml`. A key with no entry
returns a plain sentence saying so rather than an empty string, because a
blank health line reads as "fine" and that is exactly the wrong thing for
an unknown state to look like.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_LANGUAGE = Path(__file__).parent.parent / "data" / "driver_language.yaml"


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, str]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return data.get("health", {})


def say(key: str, path: str | Path = DEFAULT_LANGUAGE, **fields: Any) -> str:
    """One sentence about a driver's health, filled in."""
    template = _load(str(path)).get(key)
    if template is None:
        return f"No wording for {key}, which means this build cannot describe its own state."
    try:
        return template.format(**fields)
    except (KeyError, IndexError):
        return template
