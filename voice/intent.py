"""What the operator meant.

One schema, three answers: a question to answer, an order to read back, or
something that could mean more than one thing and therefore must be asked
about. Nothing else is a legal outcome, and in particular there is no
outcome that carries out an order.

The schema is enforced by the gateway rather than parsed out of prose,
because the difference between an order and a question is exactly the kind
of thing that must not be decided by a regular expression.

Interpretation is only half the job. Everything the language service
returns is checked here against what the world model actually contains,
because a language model naming a machine is not evidence that the machine
exists. An order that names something unknown becomes a question, never an
action.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

# What the operator can be understood to have meant.
KIND_QUESTION = "question"
KIND_ORDER = "order"
KIND_UNCLEAR = "unclear"

# The shape the gateway forces on the answer. Every field is required and
# no others are allowed, so a partially-understood order cannot arrive
# looking like a complete one.
INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [KIND_QUESTION, KIND_ORDER, KIND_UNCLEAR],
            "description": (
                "question if the operator asked something; order if they told a machine "
                "to do something; unclear if it could mean more than one thing, names "
                "something you were not given, or you are not sure."
            ),
        },
        "answer": {
            "type": "string",
            "description": (
                "For a question: the answer, in one or two plain sentences, carrying "
                "the uncertainty of the data. Empty for anything else."
            ),
        },
        "clarifying_question": {
            "type": "string",
            "description": (
                "For unclear: one short question that would resolve the ambiguity. "
                "Empty for anything else."
            ),
        },
        "readback": {
            "type": "string",
            "description": (
                "For an order: one short sentence naming the machine and what it will "
                "do, phrased so that answering yes is unambiguous. Empty otherwise."
            ),
        },
        "machine_name": {
            "type": "string",
            "description": (
                "For an order: the machine's name exactly as it appears in the data "
                "you were given. Empty otherwise."
            ),
        },
        "task_type": {
            "type": "string",
            "enum": ["navigate", "patrol", "hold", "return_home", ""],
            "description": "For an order: what the machine should do. Empty otherwise.",
        },
        "place_name": {
            "type": "string",
            "description": (
                "For an order that names somewhere to go: the place's name exactly as "
                "it appears in the data you were given. Empty otherwise."
            ),
        },
    },
    "required": [
        "kind",
        "answer",
        "clarifying_question",
        "readback",
        "machine_name",
        "task_type",
        "place_name",
    ],
    "additionalProperties": False,
}


@dataclass
class Intent:
    """What the system decided the operator meant, after checking."""

    kind: str
    # What the machine will say. Always present: a decision with nothing to
    # say is a decision the operator cannot see, and the honesty law
    # requires that everything spoken is also printed.
    speech: str = ""
    # Set only for an order that survived checking against the world.
    asset_id: str = ""
    asset_name: str = ""
    task_type: str = ""
    waypoints: list[dict[str, float]] = field(default_factory=list)
    place_name: str = ""

    @property
    def needs_confirmation(self) -> bool:
        """Only an order does, and an order always does.

        There is no confidence level at which the readback is skipped. The
        plan says voice cannot execute anything without confirmation, and
        the exception that would eventually be added is the reason to have
        no exceptions.
        """
        return self.kind == KIND_ORDER


def resolve(
    raw: dict[str, Any],
    assets: list[dict[str, Any]],
    zones: list[dict[str, Any]],
    words: dict[str, str],
    identify: Callable[[str], str] | None = None,
    locate: Callable[[str], list[dict[str, float]]] | None = None,
) -> Intent:
    """Turn what the language service said into what the system will do.

    Every name is checked against the world model. A machine or a place the
    language service invented, misheard, or hallucinated turns the order
    into a question rather than into an action.

    `identify` turns a machine's name into its identifier, and `locate`
    turns a place's name into somewhere to drive to. Both are lookups on
    this side of the gateway rather than fields in the prompt, so neither
    an identifier nor a coordinate is ever handed to a language model.
    """
    kind = raw.get("kind", KIND_UNCLEAR)

    if kind == KIND_QUESTION:
        answer = (raw.get("answer") or "").strip()
        if not answer:
            return Intent(kind=KIND_UNCLEAR, speech=words.get("not_understood", ""))
        return Intent(kind=KIND_QUESTION, speech=answer)

    if kind != KIND_ORDER:
        question = (raw.get("clarifying_question") or "").strip()
        return Intent(
            kind=KIND_UNCLEAR, speech=question or words.get("not_understood", "")
        )

    # An order. Everything below is checking, not interpreting.
    asset = _match_asset(raw.get("machine_name", ""), assets)
    if asset is None:
        # Not a refusal and not a guess. The operator is told what is
        # wrong and can say it again.
        return Intent(kind=KIND_UNCLEAR, speech=words.get("no_such_machine", ""))

    task_type = (raw.get("task_type") or "").strip()
    if not task_type:
        return Intent(kind=KIND_UNCLEAR, speech=words.get("not_understood", ""))

    waypoints: list[dict[str, float]] = []
    place_name = ""
    if task_type in ("navigate", "patrol"):
        zone = _match_zone(raw.get("place_name", ""), zones)
        if zone is None:
            return Intent(kind=KIND_UNCLEAR, speech=words.get("no_such_place", ""))
        place_name = zone.get("name", "")
        waypoints = locate(place_name) if locate else []
        if not waypoints:
            return Intent(kind=KIND_UNCLEAR, speech=words.get("no_such_place", ""))

    readback = (raw.get("readback") or "").strip()
    if not readback:
        # The readback is the whole safety mechanism. An order without one
        # is not carried out on a sentence composed here, because a
        # sentence composed here is one the operator did not agree to.
        return Intent(kind=KIND_UNCLEAR, speech=words.get("not_understood", ""))

    return Intent(
        kind=KIND_ORDER,
        speech=readback,
        asset_id=identify(asset.get("name", "")) if identify else "",
        asset_name=asset.get("name", ""),
        task_type=task_type,
        waypoints=waypoints,
        place_name=place_name,
    )


def _match_asset(name: str, assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the machine the operator meant, or nothing.

    Exact match on the displayed name first, then a forgiving one, because
    a recogniser routinely returns "scout one" for "Scout 1". Never a
    nearest guess: two machines that both loosely match is an ambiguity,
    and answering it by picking one is how the wrong machine drives away.
    """
    wanted = _normalise(name)
    if not wanted:
        return None

    exact = [a for a in assets if _normalise(a.get("name", "")) == wanted]
    if len(exact) == 1:
        return exact[0]

    # A machine with no name must never loose-match, because the empty
    # string is contained in every string and would therefore match any
    # order at all.
    loose = [
        a
        for a in assets
        if (known := _normalise(a.get("name", ""))) and (wanted in known or known in wanted)
    ]
    return loose[0] if len(loose) == 1 else None


def _match_zone(name: str, zones: list[dict[str, Any]]) -> dict[str, Any] | None:
    wanted = _normalise(name)
    if not wanted:
        return None
    exact = [z for z in zones if _normalise(z.get("name", "")) == wanted]
    if len(exact) == 1:
        return exact[0]
    loose = [
        z
        for z in zones
        if (known := _normalise(z.get("name", ""))) and (wanted in known or known in wanted)
    ]
    return loose[0] if len(loose) == 1 else None


# Spoken digits, so that "gate three" finds "Gate 3". Deliberately small:
# this is for the handful of numbers that appear in place and machine
# names, not a general number parser.
_SPOKEN_DIGITS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


def _normalise(text: str) -> str:
    words = [w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split() if w]
    return " ".join(_SPOKEN_DIGITS.get(w, w) for w in words)
