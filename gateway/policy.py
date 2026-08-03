"""Which adapters a deployment is allowed to use.

The sovereignty law: all deployment targets are air-gapped, no cloud
dependency in any mission path, and cloud adapters are permitted only in
development and demonstration profiles, never in deployed ones.

That is enforced here rather than trusted. The profile is set at install
time by an admin and is not reachable from any operator surface. A profile
that does not list an adapter cannot use it, and asking for one is refused
in a way the caller can tell apart from a failure.

The refusal is the important part. A deployed system that quietly fell back
to a cloud adapter because the local one was slow would be a system that
had broken the law without anyone noticing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

DEFAULT_PROFILES = Path(__file__).parent / "data" / "policy_profiles.yaml"

# The profile used when nothing says otherwise. Deployed, deliberately: a
# missing configuration file must fail closed, toward the air-gapped
# behaviour, never toward the one that reaches the internet.
DEFAULT_PROFILE = "deployed"


@dataclass(frozen=True)
class Profile:
    """One deployment's rules."""

    name: str
    # Adapter names this profile permits, in preference order per
    # capability. An adapter not named here does not exist as far as this
    # deployment is concerned.
    adapters: dict[str, list[str]] = field(default_factory=dict)
    # Whether adapters that leave the machine may be used at all. Kept as
    # its own flag rather than inferred from the adapter list, so the
    # intent is stated and can be asserted against.
    allows_cloud: bool = False
    description: str = ""

    def adapters_for(self, capability: str) -> list[str]:
        return list(self.adapters.get(capability, ()))


def load_profiles(path: str | Path = DEFAULT_PROFILES) -> dict[str, Profile]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    profiles: dict[str, Profile] = {}
    for name, entry in (raw.get("profiles") or {}).items():
        profiles[name] = Profile(
            name=name,
            adapters={k: list(v) for k, v in (entry.get("adapters") or {}).items()},
            allows_cloud=bool(entry.get("allows_cloud", False)),
            description=str(entry.get("description", "")),
        )
    return profiles


def active_profile_name(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    return source.get("ARGUS_AI_PROFILE", DEFAULT_PROFILE)


def load_active_profile(
    path: str | Path = DEFAULT_PROFILES, env: dict[str, str] | None = None
) -> Profile:
    """The profile this deployment runs under.

    A name that does not exist is refused rather than defaulted. Silently
    falling back would mean a typo in an install script could turn an
    air-gapped deployment into one with cloud adapters enabled.
    """
    profiles = load_profiles(path)
    name = active_profile_name(env)
    if name not in profiles:
        raise ValueError(
            f"there is no AI policy profile called {name!r}. "
            f"This deployment knows: {', '.join(sorted(profiles))}"
        )
    profile = profiles[name]
    log.info(
        "AI policy profile %r: cloud adapters %s",
        profile.name,
        "permitted" if profile.allows_cloud else "not installed",
    )
    return profile


def describe(profile: Profile) -> dict[str, Any]:
    """The profile as structured data, for the admin surface.

    Displayed, never edited from there: the plan puts the profile in the
    installer's hands and not the operator's.
    """
    return {
        "name": profile.name,
        "description": profile.description,
        "allows_cloud": profile.allows_cloud,
        "adapters": {k: list(v) for k, v in profile.adapters.items()},
    }
