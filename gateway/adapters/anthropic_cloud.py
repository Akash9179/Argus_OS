"""The cloud language adapter.

Permitted in the `dev` and `demo` policy profiles and refused in `deployed`,
because the sovereignty law allows no cloud dependency in a mission path.
It exists so the language work can be built against a strong model before
the local one is tuned.

This file and the local adapters are the only **code** that names a model
or a provider. Configuration and documentation necessarily do too: the
policy profiles list adapters by name, and an install guide has to say
what to install. The law is about what callers can see, and the effect is
that the voice service can be read end to end without learning what is
answering it.

The module is deliberately not called `anthropic.py`: that would shadow the
package it imports.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from gateway.adapters.base import register_adapter
from gateway.capabilities import Capability, GatewayError, LanguageRequest, LanguageResponse

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"

# Voice is a latency-sensitive surface and an intent is a small answer, so
# the reasoning depth is dialled down from the default. Raise it if
# ambiguity handling turns out to need more thought than this.
EFFORT = "medium"
MAX_TOKENS = 4096


class AnthropicLanguage:
    """Understanding an order, and answering a question about the world."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str = MODEL):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._model = model
        self._client = None

    def capabilities(self) -> set[Capability]:
        return {Capability.UNDERSTAND_ORDER, Capability.ANSWER_QUESTION}

    @property
    def leaves_the_machine(self) -> bool:
        return True

    def available(self) -> tuple[bool, str]:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "the cloud client library is not installed"
        if not self._api_key:
            return False, "no API key is configured"
        return True, "ready"

    def _ensure_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def understand(self, request: LanguageRequest) -> LanguageResponse:
        ok, why = self.available()
        if not ok:
            raise GatewayError(f"cannot reach the language service: {why}")

        client = self._ensure_client()
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": request.character_prompt,
            "output_config": {"effort": EFFORT},
            "messages": self._messages(request),
        }
        if request.schema is not None:
            # A decision, not prose. The schema is enforced by the service
            # rather than parsed hopefully out of a paragraph, which is what
            # keeps an ambiguous order from being read as a confident one.
            params["output_config"]["format"] = {
                "type": "json_schema",
                "schema": request.schema,
            }

        try:
            response = client.messages.create(**params)
        except Exception as exc:
            raise GatewayError(f"the language service did not answer: {exc}") from exc

        # Checked before reading content, because a declined request returns
        # a normal response whose content is empty or partial. Reading it
        # blindly would turn a refusal into a silently truncated order.
        if response.stop_reason == "refusal":
            raise GatewayError("the language service declined to answer that")

        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise GatewayError("the language service returned nothing")

        data = None
        if request.schema is not None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise GatewayError(f"the language service returned unreadable data: {exc}") from exc

        return LanguageResponse(text=text, data=data)

    @staticmethod
    def _messages(request: LanguageRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for turn in request.history:
            role = "assistant" if turn.get("role") == "machine" else "user"
            messages.append({"role": role, "content": turn.get("text", "")})

        # The world goes in the last user turn rather than the system prompt
        # on purpose: the system prompt is the character sheet and stays
        # byte-identical between requests, so it caches. The world changes
        # every time and would invalidate that cache from the front.
        content = request.utterance
        if request.world:
            content = (
                "Here is what is true right now:\n"
                f"{json.dumps(request.world, indent=2, default=str)}\n\n"
                f"The operator said: {request.utterance}"
            )
        messages.append({"role": "user", "content": content})
        return messages


register_adapter("anthropic", AnthropicLanguage)
