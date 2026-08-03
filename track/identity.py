"""Identity and permissions.

Version 1 is deliberately trivial: bearer tokens mapped to a principal and
one of two roles. What matters is that the enforcement point exists on every
interface now, because retrofitting a permission boundary after third-party
applications exist is not feasible. The policy can grow; the boundary cannot
be added later.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

import yaml

ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"

# Admin implies every operator permission. Roles are compared through
# has_role() so this stays the single place the hierarchy is expressed.
_ROLE_IMPLIES = {ROLE_ADMIN: {ROLE_ADMIN, ROLE_OPERATOR}, ROLE_OPERATOR: {ROLE_OPERATOR}}


@dataclass(frozen=True)
class Principal:
    """An authenticated caller."""

    principal_id: str
    display_name: str
    role: str

    def has_role(self, required: str) -> bool:
        return required in _ROLE_IMPLIES.get(self.role, set())


class TokenDirectory:
    """Bearer tokens loaded from a data file, never from code."""

    def __init__(self, tokens: dict[str, Principal]):
        self._tokens = tokens

    @classmethod
    def from_file(cls, path: str | Path) -> "TokenDirectory":
        """Load tokens from YAML, creating a starter file if none exists."""
        p = Path(path)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            starter = {
                "tokens": [
                    {
                        "token": secrets.token_urlsafe(24),
                        "principal_id": "operator-1",
                        "display_name": "Operator",
                        "role": ROLE_OPERATOR,
                    },
                    {
                        "token": secrets.token_urlsafe(24),
                        "principal_id": "admin-1",
                        "display_name": "Administrator",
                        "role": ROLE_ADMIN,
                    },
                ]
            }
            p.write_text(yaml.safe_dump(starter, sort_keys=False))

        raw = yaml.safe_load(p.read_text()) or {}
        tokens: dict[str, Principal] = {}
        for entry in raw.get("tokens", []):
            tokens[entry["token"]] = Principal(
                principal_id=entry["principal_id"],
                # No fallback to the identifier: an unnamed principal is
                # better described in plain words than printed as an id.
                display_name=entry.get("display_name", ""),
                role=entry.get("role", ROLE_OPERATOR),
            )
        return cls(tokens)

    def lookup(self, token: str) -> Principal | None:
        return self._tokens.get(token)

    def display_name(self, principal_id: str) -> str:
        """What to call a person on screen.

        Operators read names, never identifiers. An identifier that has no
        matching person is still not shown: the caller gets a plain word
        instead, because a stray identifier on screen is a leak whether or
        not we recognise it.
        """
        for principal in self._tokens.values():
            if principal.principal_id == principal_id:
                return principal.display_name
        return ""
