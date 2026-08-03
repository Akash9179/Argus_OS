"""ARGUS AI gateway.

Every intelligence request in the system flows through here, and no code
outside this package may name a model or a provider. That is the gateway
law. The practical effect is that swapping providers, or moving from a
cloud model on the bench to a local one in the field, is a configuration
change rather than a code change.
"""

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
from gateway.policy import Profile, load_active_profile, load_profiles
from gateway.service import Gateway

# Registering the adapters this build carries. The import side effect is
# deliberate: an adapter that exists but is unregistered is invisible to
# the policy profile, which would make the profile a lie.
from gateway import adapters as _adapters  # noqa: E402,F401  isort:skip

__all__ = [
    "Capability",
    "CapabilityUnavailable",
    "Gateway",
    "GatewayError",
    "LanguageRequest",
    "LanguageResponse",
    "Profile",
    "Speech",
    "SpeechRequest",
    "Transcription",
    "TranscriptionRequest",
    "load_active_profile",
    "load_profiles",
]
