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
        # `allows_cloud` is published because it is the policy itself, and a
        # caller checking sovereignty has to be able to read the rule rather
        # than infer it from this method's own conclusions. Inferring it is
        # circular: this method sets `usable` to False for exactly the
        # adapters a caller would be looking for, so a check written against
        # `usable` can never fail.
        report: dict[str, Any] = {
            "profile": self.profile.name,
            "allows_cloud": self.profile.allows_cloud,
            "capabilities": {},
        }
        # Every capability the enum knows, and then every key the profile
        # names that the enum does not. A profile may carry a capability from
        # a newer build, or a misspelled one; the adapters under it are
        # carried either way, so they are enumerated either way. Skipping
        # them would let a cloud adapter hide under an unknown key while the
        # aggregate below says everything is known local, which is the exact
        # overclaim the aggregate exists to prevent.
        capability_names = [capability.value for capability in Capability]
        capability_names += [
            key for key in self.profile.adapters if key not in capability_names
        ]
        for capability_name in capability_names:
            entries = []
            for name in self.profile.adapters_for(capability_name):
                try:
                    adapter = self._adapter(name)
                except CapabilityUnavailable as exc:
                    # Whether it would have left the machine is unknown: the
                    # adapter was never constructed. None says that, where
                    # False would be a claim.
                    entries.append(
                        {
                            "adapter": name,
                            "usable": False,
                            "detail": str(exc),
                            "leaves_the_machine": None,
                        }
                    )
                    continue
                usable, detail = adapter.available()
                if usable and adapter.leaves_the_machine and not self.profile.allows_cloud:
                    usable, detail = False, "refused: this profile does not permit cloud adapters"
                # Published so a caller can check the sovereignty claim rather
                # than trust it. An installer verifying a deployed target has
                # to be able to see that nothing usable leaves the machine,
                # and a check that cannot see it is a check that cannot fail.
                entries.append(
                    {
                        "adapter": name,
                        "usable": usable,
                        "detail": detail,
                        "leaves_the_machine": adapter.leaves_the_machine,
                    }
                )
            report["capabilities"][capability_name] = entries

        # The whole sovereignty question, answered once, by the process that
        # actually holds the adapters. True: something in this deployment
        # would send data off the machine. False: everything is known local.
        # None: at least one adapter could not be constructed, so the claim
        # cannot be made either way, and saying False here would be saying
        # more than is known. A verifier must treat None as a failure on a
        # deployed target: an unverifiable sovereignty claim is not a
        # satisfied one.
        #
        # Computed here and not by callers, because a caller enumerating the
        # entries in its own process reads its own environment. That exact
        # mistake shipped three times in the install verification before this
        # field existed.
        flags = [
            entry["leaves_the_machine"]
            for entries in report["capabilities"].values()
            for entry in entries
        ]
        if any(flag is True for flag in flags):
            report["anything_leaves_the_machine"] = True
        elif any(flag is None for flag in flags):
            report["anything_leaves_the_machine"] = None
        else:
            report["anything_leaves_the_machine"] = False

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
