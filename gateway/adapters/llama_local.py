"""The local language adapter: the deployed path.

Speaks the OpenAI-compatible HTTP interface that llama.cpp, Ollama and vLLM
all serve, so what runs behind it is a deployment choice rather than a code
one: llama.cpp on a laptop, vLLM on the ground station, either of them on
the machine itself.

**No model has been chosen and none has been licence-verified.** The
licensing law requires verifying every third-party licence for military use
before integration, and that has not been done for any set of weights. So
this adapter carries no default model: an installer must name one, having
verified it and recorded it in LICENSES.md. Defaulting would mean a
deployment quietly running weights nobody checked, which is the exact
failure the law exists to prevent. Meta Llama is already disqualified by
the plan for its military-use carve-out.

Status: **this adapter is real and unexercised.** Stage 4 was built with no
local model installed, so the code path exists, is configured, and has
never answered a request. That is recorded here rather than in a commit
message because a reader deciding whether to trust the air-gapped story
needs to know which parts have run.

It is the only local-language adapter, and in the `deployed` profile it is
the only language adapter of any kind.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from gateway.adapters.base import register_adapter
from gateway.capabilities import Capability, GatewayError, LanguageRequest, LanguageResponse

log = logging.getLogger(__name__)

DEFAULT_ENDPOINT = os.getenv("ARGUS_LOCAL_LLM", "http://127.0.0.1:11434/v1")
# Deliberately no fallback. See the module docstring: an unverified model
# arriving by default is a licensing failure, not a convenience.
DEFAULT_MODEL = os.getenv("ARGUS_LOCAL_MODEL", "")


class LlamaLocal:
    """A local model, reached over the interface every local server speaks."""

    name = "llama_local"

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 60.0,
    ):
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._timeout = timeout_s

    def capabilities(self) -> set[Capability]:
        return {Capability.UNDERSTAND_ORDER, Capability.ANSWER_QUESTION}

    @property
    def leaves_the_machine(self) -> bool:
        """Whether this endpoint is actually on the machine.

        Not a constant. The endpoint comes from configuration, and
        `ARGUS_LOCAL_LLM` pointed at a remote host would ship every
        operator utterance and the whole world view off the machine while
        an adapter that hardcoded `False` reported it as local. The name
        of a thing is not evidence about where it runs, so this is
        answered by looking at the address.
        """
        return not _is_on_this_machine(self._endpoint)

    def available(self) -> tuple[bool, str]:
        if not self._model:
            return (
                False,
                "no model has been chosen and verified. Set ARGUS_LOCAL_MODEL to a "
                "model whose licence you have checked and recorded in LICENSES.md.",
            )
        if self.leaves_the_machine:
            # Said plainly at boot rather than discovered by a reviewer.
            # The gateway will refuse it under a profile that forbids
            # cloud, but a deployment should learn this from its own
            # startup check, not from an audit.
            log.warning(
                "the local model endpoint %s is not on this machine", self._endpoint
            )
        try:
            with urllib.request.urlopen(f"{self._endpoint}/models", timeout=2.0) as response:
                if response.status != 200:
                    return False, f"the local model server answered {response.status}"
        except (urllib.error.URLError, OSError) as exc:
            return False, f"no local model server at {self._endpoint} ({exc})"
        return True, "ready"

    def understand(self, request: LanguageRequest) -> LanguageResponse:
        ok, why = self.available()
        if not ok:
            raise GatewayError(f"cannot reach the local model: {why}")

        messages = [{"role": "system", "content": request.character_prompt}]
        for turn in request.history:
            role = "assistant" if turn.get("role") == "machine" else "user"
            messages.append({"role": role, "content": turn.get("text", "")})

        content = request.utterance
        if request.world:
            content = (
                "Here is what is true right now:\n"
                f"{json.dumps(request.world, indent=2, default=str)}\n\n"
                f"The operator said: {request.utterance}"
            )
        messages.append({"role": "user", "content": content})

        payload: dict[str, Any] = {"model": self._model, "messages": messages, "stream": False}
        if request.schema is not None:
            # The same servers accept a JSON schema here, though smaller
            # models honour it less reliably than a large one does. The
            # voice service therefore validates every field it depends on
            # rather than trusting the shape it asked for.
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "intent", "schema": request.schema, "strict": True},
            }

        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._endpoint}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                answer = json.loads(response.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise GatewayError(f"the local model did not answer: {exc}") from exc

        try:
            text = answer["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise GatewayError(f"the local model returned an unexpected shape: {exc}") from exc

        data = None
        if request.schema is not None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise GatewayError(f"the local model returned unreadable data: {exc}") from exc

        return LanguageResponse(text=text, data=data)


def _is_on_this_machine(endpoint: str) -> bool:
    """True only for an address that cannot leave the box.

    Loopback and nothing else. A private-range address is still a
    different machine on a network, and under the sovereignty law "did not
    leave the building" is not the same claim as "did not leave the
    machine". A deployment that genuinely wants a model on a nearby host
    should say so in its policy profile rather than have this function
    quietly agree.
    """
    try:
        host = urllib.parse.urlparse(endpoint).hostname or ""
    except ValueError:
        return False
    if host in ("localhost", "::1"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


register_adapter("llama_local", LlamaLocal)
