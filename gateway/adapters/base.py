"""What an adapter is.

An adapter serves one or more capabilities using one provider. It is the
only kind of object in this system allowed to know a model name, and the
gateway is the only package allowed to contain one.

Adapters declare rather than assume:

* which capabilities they serve, so a profile listing an adapter that
  cannot do the job is caught at startup rather than at the moment an
  operator speaks;
* whether they leave the machine, so the sovereignty law can be enforced
  by the registry instead of by everyone remembering;
* whether they are actually usable right now, so a missing API key or an
  uninstalled binary is a clear message at boot and not a stack trace
  mid-sentence.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gateway.capabilities import (
    Capability,
    LanguageRequest,
    LanguageResponse,
    Speech,
    SpeechRequest,
    Transcription,
    TranscriptionRequest,
)


@runtime_checkable
class Adapter(Protocol):
    """One provider, one or more capabilities."""

    name: str

    def capabilities(self) -> set[Capability]: ...

    @property
    def leaves_the_machine(self) -> bool:
        """True when using this adapter sends data off the machine.

        Declared by the adapter rather than inferred from its name,
        because the name of the next provider is not known here and a rule
        based on a list of known cloud vendors fails open.
        """
        ...

    def available(self) -> tuple[bool, str]:
        """Whether it can be used, and a sentence saying why not."""
        ...


class LanguageAdapter(Adapter, Protocol):
    def understand(self, request: LanguageRequest) -> LanguageResponse: ...


class TranscribeAdapter(Adapter, Protocol):
    def transcribe(self, request: TranscriptionRequest) -> Transcription: ...


class SpeakAdapter(Adapter, Protocol):
    def speak(self, request: SpeechRequest) -> Speech: ...


# name -> adapter class. Adapters register on import, the same pattern the
# HAL uses for drivers, and for the same reason: a thing that exists but is
# unregistered is invisible to configuration, which makes the configuration
# a lie.
_ADAPTERS: dict[str, type] = {}


def register_adapter(name: str, adapter: type) -> None:
    _ADAPTERS[name] = adapter


def known_adapters() -> dict[str, type]:
    return dict(_ADAPTERS)
