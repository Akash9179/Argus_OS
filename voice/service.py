"""The voice service.

Push to talk, and what happens next. Four steps: hear, understand, say,
and, for an order, wait to be confirmed.

Three rules shape this file:

* **Everything heard and everything spoken is printed.** The honesty law
  and the audit trail both require it, and an operator in a noisy vehicle
  needs it. So every exchange returns its text alongside its audio, and
  the text is what the record keeps.
* **Voice executes nothing without a readback.** An order becomes a
  pending exchange and a sentence to confirm. Nothing reaches the world
  model until the operator says yes.
* **Voice uses the same interfaces an application uses.** Orders go
  through the ordinary task endpoint with the operator's own credentials,
  so `issued_by` records the person and the voice path. The SDK honesty
  law forbids a private route, and a private route would also mean voice
  orders were auditable differently from map orders.

The service reaches the world model over its public HTTP interface rather
than importing it, because voice is a separate deployable and the day it
runs on a different host should not be the day this file changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gateway import (
    Capability,
    CapabilityUnavailable,
    Gateway,
    GatewayError,
    LanguageRequest,
    SpeechRequest,
    TranscriptionRequest,
)
from voice import intent as intents
from voice.world import NotSignedIn, WorldUnavailable

log = logging.getLogger(__name__)

CHARACTER_DIR = Path(__file__).parent / "characters"
DEFAULT_CHARACTER = "ops"

# How long a readback waits for an answer before it is forgotten. An order
# confirmed five minutes after it was proposed is an order confirmed
# against a world that has moved.
PENDING_TTL_S = 120.0


@dataclass
class Character:
    """A personality, loaded from data."""

    name: str
    prompt: str
    fallbacks: dict[str, str] = field(default_factory=dict)
    speaker: int = 0

    def say(self, key: str) -> str:
        return self.fallbacks.get(key, "")


def load_character(name: str = DEFAULT_CHARACTER, directory: Path = CHARACTER_DIR) -> Character:
    path = directory / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"there is no character sheet called {name!r}")
    raw = yaml.safe_load(path.read_text()) or {}
    return Character(
        name=raw.get("name", name),
        prompt=raw.get("prompt", ""),
        fallbacks=raw.get("fallbacks", {}) or {},
        speaker=int((raw.get("voice") or {}).get("speaker", 0)),
    )


def available_characters(directory: Path = CHARACTER_DIR) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.yaml"))


@dataclass
class Pending:
    """An order proposed and not yet confirmed."""

    exchange_id: str
    intent: intents.Intent
    created_at: float


@dataclass
class Exchange:
    """One turn of the conversation, as the operator sees it.

    `heard` and `spoken` are both here and both always populated, because
    the honesty law says spoken output is always also shown as text.
    """

    exchange_id: str
    heard: str
    spoken: str
    kind: str
    needs_confirmation: bool = False
    audio: bytes | None = None
    audio_format: str = "wav"
    # Present on an order, so C2 can show what it is about to do.
    action: dict[str, Any] | None = None


class VoiceService:
    """The voice layer, between an operator and the world model."""

    def __init__(
        self,
        gateway: Gateway,
        world,
        character: Character | None = None,
        speak_replies: bool = True,
        pending: dict[str, Pending] | None = None,
        caller: str = "",
    ):
        self.gateway = gateway
        self.world = world
        self.character = character or load_character()
        self._speak = speak_replies
        # Readbacks outlive the request that proposed them: the operator
        # speaks on one request and answers on the next. An instance-local
        # store would therefore lose every pending order between the two,
        # and every confirmation would find nothing to confirm. The store
        # is injected so the interface can hold one for the process.
        self._pending: dict[str, Pending] = {} if pending is None else pending
        # Keys are namespaced per caller so one signed-in operator can
        # never confirm an order another operator was asked about.
        self._caller = caller

    # -- the exchange ------------------------------------------------------

    async def listen(self, audio: bytes, audio_format: str = "wav") -> Exchange:
        """Audio in, an exchange out."""
        try:
            # Hearing shells out to a recogniser, so it runs off the event
            # loop. A voice service that blocked while transcribing would
            # stop serving every other operator for the length of a clip.
            transcription = await asyncio.to_thread(
                self.gateway.transcribe,
                TranscriptionRequest(audio=audio, audio_format=audio_format),
            )
            heard = transcription.text
        except GatewayError as exc:
            log.warning("could not hear: %s", exc)
            return await self._reply("", self.character.say("cannot_think"), intents.KIND_UNCLEAR)

        if not heard.strip():
            return await self._reply("", self.character.say("nothing_heard"), intents.KIND_UNCLEAR)

        return await self.interpret(heard)

    async def interpret(self, heard: str) -> Exchange:
        """Text in, an exchange out. Split from `listen` so the language
        half can be exercised without a microphone."""
        try:
            world = await self._world_view()
        except WorldUnavailable as exc:
            # Not "there is no such machine". The world model could not be
            # asked, and saying anything about what it contains would be a
            # confident claim about something unknown.
            log.warning("could not read the world: %s", exc)
            return await self._reply(
                heard, self.character.say("cannot_see"), intents.KIND_UNCLEAR
            )

        try:
            answer = await asyncio.to_thread(
                self.gateway.understand_order,
                LanguageRequest(
                    character_prompt=self.character.prompt,
                    utterance=heard,
                    world=world,
                    schema=intents.INTENT_SCHEMA,
                ),
            )
        except CapabilityUnavailable as exc:
            # Refused by policy, not broken. The operator is told the voice
            # is unavailable and that the map still works, which is true
            # and is the thing they need to know.
            log.warning("no language adapter: %s", exc)
            return await self._reply(
                heard, self.character.say("cannot_think"), intents.KIND_UNCLEAR
            )
        except GatewayError as exc:
            log.warning("could not understand: %s", exc)
            return await self._reply(
                heard, self.character.say("cannot_think"), intents.KIND_UNCLEAR
            )

        if answer.data is None:
            return await self._reply(
                heard, self.character.say("not_understood"), intents.KIND_UNCLEAR
            )

        decided = intents.resolve(
            answer.data,
            assets=world.get("machines", []),
            zones=world.get("places", []),
            words=self.character.fallbacks,
            # Not getattr-with-a-default: a world model without these
            # would silently resolve every order to an empty identifier
            # and post it to the task endpoint, which is a worse failure
            # than an import error at startup.
            identify=self.world.identify,
            locate=self.world.waypoints_for,
        )
        return await self._from_intent(heard, decided)

    def _key(self, exchange_id: str) -> str:
        return f"{self._caller}:{exchange_id}"

    async def confirm(self, exchange_id: str, confirmed: bool) -> Exchange:
        """Answer a readback. This is the only path that acts."""
        self._forget_stale()
        pending = self._pending.pop(self._key(exchange_id), None)
        if pending is None:
            # Either already answered, or too old. Saying so is better than
            # acting on an order whose moment has passed.
            return await self._reply("", self.character.say("cancelled"), intents.KIND_UNCLEAR)

        if not confirmed:
            return await self._reply("", self.character.say("cancelled"), intents.KIND_UNCLEAR)

        try:
            await self._issue(pending.intent)
        except Exception:
            # The exception is logged, never spoken. A raw HTTP error read
            # aloud would put a URL, a status code and an internal port
            # through the waterline and into an operator's ear.
            log.exception("could not issue a voice order")
            return await self._reply(
                "", self.character.say("order_refused"), intents.KIND_UNCLEAR
            )

        return await self._reply("", self.character.say("confirmed"), intents.KIND_ORDER)

    # -- the world ---------------------------------------------------------

    async def _world_view(self) -> dict[str, Any]:
        """What the language service is allowed to know.

        Deliberately small and already in operator words. The gateway is a
        translation service, not a participant, so it gets what it needs to
        interpret a sentence and nothing else. Sending the whole world
        model would be slower, more expensive, and would hand a language
        service more than it needs to do its job.
        """
        return await self.world.view()

    async def _issue(self, decided: intents.Intent) -> None:
        await self.world.create_task(
            asset_id=decided.asset_id,
            task_type=decided.task_type,
            waypoints=decided.waypoints,
        )

    # -- shaping the reply -------------------------------------------------

    async def _from_intent(self, heard: str, decided: intents.Intent) -> Exchange:
        exchange = await self._reply(heard, decided.speech, decided.kind)
        if decided.needs_confirmation:
            self._pending[self._key(exchange.exchange_id)] = Pending(
                exchange_id=exchange.exchange_id,
                intent=decided,
                created_at=time.monotonic(),
            )
            exchange.needs_confirmation = True
            exchange.action = {
                "machine": decided.asset_name,
                "task_type": decided.task_type,
                "place": decided.place_name,
            }
        return exchange

    async def _reply(self, heard: str, spoken: str, kind: str) -> Exchange:
        exchange = Exchange(
            exchange_id=str(uuid.uuid4()),
            heard=heard,
            spoken=spoken,
            kind=kind,
        )
        if self._speak and spoken:
            try:
                speech = await asyncio.to_thread(
                    self.gateway.speak,
                    SpeechRequest(text=spoken, character=self.character.name),
                )
                exchange.audio = speech.audio
                exchange.audio_format = speech.audio_format
            except GatewayError as exc:
                # A voice that cannot speak still answers. The text is the
                # record; the audio is a convenience, and losing it must
                # not lose the reply.
                log.warning("could not speak: %s", exc)
        return exchange

    def _forget_stale(self) -> None:
        now = time.monotonic()
        for key in [
            k for k, p in self._pending.items() if now - p.created_at > PENDING_TTL_S
        ]:
            del self._pending[key]

    @property
    def pending_count(self) -> int:
        """How many readbacks this caller is waiting to answer."""
        self._forget_stale()
        return sum(1 for key in self._pending if key.startswith(f"{self._caller}:"))
