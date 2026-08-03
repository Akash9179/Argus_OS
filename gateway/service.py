"""The AI gateway.

One service through which every intelligence request flows. Callers ask for
a capability; the gateway picks an adapter the policy profile permits, and
the caller never learns which one answered.

Two rules are enforced here rather than trusted:

* A capability with no permitted adapter is **refused**, and the refusal is
  a distinct kind of error from a failure. A deployed profile with no cloud
  adapters is working correctly, and a caller must be able to tell that
  apart from something being broken.
* An adapter that leaves the machine is **never** used under a profile that
  does not allow cloud. Checked per request, against the adapter's own
  declaration, not against a list of provider names. A rule that had to
  recognise the next cloud vendor by name would fail open the first time
  someone added one.

The second check is the sovereignty law in code. It is deliberately
redundant with the profile's adapter list: a profile that named a cloud
adapter by mistake would still be refused at the point of use.
"""

from __future__ import annotations

import logging
from typing import Any

from gateway.adapters import base
from gateway.capabilities import (
    Capability,
    CapabilityUnavailable,
    GatewayError,
    LanguageRequest,
    LanguageResponse,
    Speech,
    SpeechRequest,
    Transcription,
    TranscriptionRequest,
)
from gateway.policy import Profile, load_active_profile

log = logging.getLogger(__name__)


class Gateway:
    """Capability in, answer out. The provider stays inside."""

    def __init__(self, profile: Profile | None = None, adapters: dict[str, Any] | None = None):
        self.profile = profile or load_active_profile()
        self._built: dict[str, Any] = dict(adapters or {})
        self._checked = False

    # -- wiring ------------------------------------------------------------

    def _adapter(self, name: str):
        if name not in self._built:
            factory = base.known_adapters().get(name)
            if factory is None:
                raise CapabilityUnavailable(
                    f"this build has no adapter called {name!r}. "
                    f"It carries: {', '.join(sorted(base.known_adapters()))}"
                )
            self._built[name] = factory()
        return self._built[name]

    def check(self) -> dict[str, Any]:
        """What this deployment can actually do, and what it cannot.

        Run at startup so a missing model or an absent key is a sentence in
        the log at boot rather than a failure the first time an operator
        speaks.
        """
        report: dict[str, Any] = {"profile": self.profile.name, "capabilities": {}}
        for capability in Capability:
            entries = []
            for name in self.profile.adapters_for(capability.value):
                try:
                    adapter = self._adapter(name)
                except CapabilityUnavailable as exc:
                    entries.append({"adapter": name, "usable": False, "detail": str(exc)})
                    continue
                usable, detail = adapter.available()
                if usable and adapter.leaves_the_machine and not self.profile.allows_cloud:
                    usable, detail = False, "refused: this profile does not permit cloud adapters"
                entries.append({"adapter": name, "usable": usable, "detail": detail})
            report["capabilities"][capability.value] = entries

        self._checked = True
        for capability, entries in report["capabilities"].items():
            if not any(entry["usable"] for entry in entries):
                log.warning(
                    "no usable adapter for %s under profile %r: %s",
                    capability,
                    self.profile.name,
                    "; ".join(f"{e['adapter']} ({e['detail']})" for e in entries) or "none listed",
                )
        return report

    def _pick(self, capability: Capability):
        """The first permitted, installed, healthy adapter for the job."""
        names = self.profile.adapters_for(capability.value)
        if not names:
            raise CapabilityUnavailable(
                f"the {self.profile.name!r} profile has no adapter for {capability.value}"
            )

        reasons = []
        for name in names:
            adapter = self._adapter(name)

            # The sovereignty check, at the point of use. Redundant with the
            # profile's list on purpose: a profile that named a cloud
            # adapter by mistake is still refused here.
            if adapter.leaves_the_machine and not self.profile.allows_cloud:
                reasons.append(f"{name} would leave the machine, which this profile forbids")
                continue

            if capability not in adapter.capabilities():
                reasons.append(f"{name} does not do {capability.value}")
                continue

            usable, detail = adapter.available()
            if not usable:
                reasons.append(f"{name}: {detail}")
                continue
            return adapter

        raise CapabilityUnavailable(
            f"nothing can do {capability.value} right now. Tried: {'; '.join(reasons)}"
        )

    # -- capabilities ------------------------------------------------------

    def transcribe(self, request: TranscriptionRequest) -> Transcription:
        return self._pick(Capability.TRANSCRIBE).transcribe(request)

    def speak(self, request: SpeechRequest) -> Speech:
        return self._pick(Capability.SPEAK).speak(request)

    def understand_order(self, request: LanguageRequest) -> LanguageResponse:
        return self._pick(Capability.UNDERSTAND_ORDER).understand(request)

    def answer_question(self, request: LanguageRequest) -> LanguageResponse:
        return self._pick(Capability.ANSWER_QUESTION).understand(request)

    # -- for the admin surface ---------------------------------------------

    def describe(self) -> dict[str, Any]:
        """What the deployment is running, for an admin to read.

        Adapter names appear here. That is admin-facing by design: the
        waterline law keeps this away from operators, and an administrator
        who cannot find out what their own deployment is running has been
        given a black box rather than a system.
        """
        from gateway.policy import describe as describe_profile

        return {"policy": describe_profile(self.profile), "check": self.check()}


__all__ = [
    "Capability",
    "CapabilityUnavailable",
    "Gateway",
    "GatewayError",
    "LanguageRequest",
    "LanguageResponse",
    "Speech",
    "SpeechRequest",
    "Transcription",
    "TranscriptionRequest",
]
