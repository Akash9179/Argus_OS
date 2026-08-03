"""What callers may ask for.

The gateway law: no code outside this package may name a model or a
provider. The consequence is that callers ask for a capability, never for a
model, and this file is the list of capabilities that exist.

A capability is a job, described in the caller's terms: turn speech into
text, turn an order into an intent, say this out loud. What answers it is
an adapter, chosen by the policy profile, and the caller never learns which
one answered.

Adding a capability is adding an entry here and an adapter that serves it.
Adding a provider is adding an adapter. Neither is a change to any caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Capability(str, Enum):
    """The jobs the gateway can do."""

    # Speech in. Audio bytes to a transcript.
    TRANSCRIBE = "transcribe"

    # Speech out. Text to audio bytes.
    SPEAK = "speak"

    # Language. A spoken order plus what the world currently looks like,
    # turned into a decision about what was meant.
    UNDERSTAND_ORDER = "understand_order"

    # Language. A question about the world, answered in plain sentences
    # that carry their own uncertainty.
    ANSWER_QUESTION = "answer_question"


@dataclass(frozen=True)
class TranscriptionRequest:
    audio: bytes
    # Container the audio arrived in, for example "wav" or "webm". The
    # adapter converts; callers are not asked to.
    audio_format: str = "wav"


@dataclass(frozen=True)
class Transcription:
    text: str
    # How sure the recogniser is, 0.0 to 1.0, or None when it will not say.
    # None is not zero, and it is not one: it means the question has no
    # answer from this adapter, and the honesty law says callers must be
    # able to tell the difference.
    confidence: float | None = None


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    # Which character is speaking. The gateway maps this to a voice; the
    # caller never names one.
    character: str = "ops"


@dataclass(frozen=True)
class Speech:
    audio: bytes
    audio_format: str
    # Always returned alongside the audio, because the honesty law requires
    # that everything spoken is also printed. Returning them together makes
    # it awkward to print nothing.
    text: str


@dataclass(frozen=True)
class LanguageRequest:
    """A language job, described without naming anything that answers it."""

    # The character sheet's system prompt. Personality is data owned by the
    # caller, not a property of a model.
    character_prompt: str
    # What the operator said, or asked.
    utterance: str
    # What the world looks like right now, already reduced to what matters.
    # The gateway does not read the world model itself: it is a translation
    # service, not a participant.
    world: dict[str, Any] = field(default_factory=dict)
    # The exchange so far, oldest first, as {"role": ..., "text": ...}.
    history: list[dict[str, str]] = field(default_factory=list)
    # The shape the answer must take, as JSON Schema, when the caller needs
    # a decision rather than prose.
    schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class LanguageResponse:
    text: str
    # Present when the request carried a schema and the adapter honoured it.
    data: dict[str, Any] | None = None


class GatewayError(RuntimeError):
    """The gateway could not answer.

    Raised in plain terms, because a voice layer that cannot reach the
    gateway has to tell an operator something true and short.
    """


class CapabilityUnavailable(GatewayError):
    """No adapter in this policy profile serves that capability.

    Its own type because it is not a fault: a deployed profile with no
    cloud adapters is working exactly as designed, and the caller needs to
    distinguish "refused by policy" from "broken".
    """
