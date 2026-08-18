"""Who is allowed to drive, by name.

One shared password meant the log could never say who was holding the
wheel, and revoking one person meant re-keying everyone. Per-operator
tokens fix both (ADR-0009): each person gets their own secret, mapped to
an identity that follows them into the session log.

Deliberately shaped like TRACK's token directory (track/identity.py), so
the two converge into one identity story later instead of growing apart.
The differences are honest ones: this daemon is stdlib-only, so the file
is JSON rather than YAML, and there are no roles here because DRIVER and
SPECTATOR are seat order, not identity.

Tokens live in a data file, never in code, and never in the log.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Operator:
    """An authenticated person at the wheel or watching."""

    operator_id: str
    display_name: str


class OperatorDirectory:
    """Bearer tokens mapped to operators, loaded from a data file."""

    def __init__(self, operators: dict[str, Operator]):
        # An empty token would authenticate a client that sent no secret
        # at all (the daemon reads a missing field as ""). A directory
        # that could contain one is refused before it can.
        if any(not token for token in operators):
            raise ValueError("an operator token must not be empty")
        self._operators = operators

    def __len__(self) -> int:
        return len(self._operators)

    @classmethod
    def from_file(cls, path: str | Path) -> "OperatorDirectory":
        """Load operators from JSON, creating a starter file if none exists."""
        p = Path(path)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            starter = {
                "operators": [
                    {
                        "token": secrets.token_urlsafe(24),
                        "operator_id": "operator-1",
                        "display_name": "Operator",
                    }
                ]
            }
            p.write_text(json.dumps(starter, indent=2) + "\n")
            # The file holds live bearer tokens; nobody else on the
            # machine has any business reading it.
            p.chmod(0o600)

        raw = json.loads(p.read_text()) or {}
        operators: dict[str, Operator] = {}
        for entry in raw.get("operators", []):
            token = entry["token"]
            if token in operators:
                # Two people, one token would mean the log attributes one
                # person's driving to the other. Refuse the file instead.
                raise ValueError("duplicate operator token in " + str(p))
            operators[token] = Operator(
                operator_id=entry["operator_id"],
                display_name=entry.get("display_name", ""),
            )
        return cls(operators)

    def lookup(self, token: str) -> Operator | None:
        return self._operators.get(token)
