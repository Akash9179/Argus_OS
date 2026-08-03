"""Adapters: one per provider, and the only place a provider is named.

Importing this package registers every adapter this build carries. Which of
them a deployment may actually use is the policy profile's decision, not
this file's: an adapter being present is not permission to use it.

The cloud adapter is registered **only if its client library is present**.
Plan section 7 says a deployed profile has cloud adapters *not installed*,
not merely refused, so a deployed image simply does not carry the
dependency and the adapter never registers. The gateway's runtime refusal
stays as the second line of defence for a build that does carry it.
"""

import logging

from gateway.adapters import llama_local as _llama  # noqa: F401
from gateway.adapters import speech_local as _speech  # noqa: F401

log = logging.getLogger(__name__)

try:  # pragma: no cover - depends on how the build was installed
    import anthropic as _sdk  # noqa: F401
except ImportError:
    log.debug("no cloud language client installed; the cloud adapter is not registered")
else:
    from gateway.adapters import anthropic_cloud as _anthropic  # noqa: F401
