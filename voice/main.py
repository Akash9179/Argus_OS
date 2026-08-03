"""The voice service, as an interface.

    ARGUS_AI_PROFILE=dev .venv/bin/python -m voice.main

Its own process on its own port, not part of the world model server. C2
consumes the world model's interfaces and the voice service's, and keeping
them apart is what stops voice from quietly reaching into the store
instead of using the interfaces every other application has to use.

Authentication is the operator's own token, forwarded to the world model on
every call. The voice service holds no credentials of its own and can do
nothing an operator could not do.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from fastapi import Body, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from gateway import Gateway
from voice.service import VoiceService, available_characters, load_character
from voice.world import DEFAULT_TRACK, NotAllowed, NotSignedIn, WorldModel, WorldUnavailable

log = logging.getLogger("voice")

REFUSALS = Path(__file__).parent / "data" / "refusals.yaml"


@lru_cache(maxsize=2)
def _refusal(key: str, path: str = str(REFUSALS)) -> str:
    """A refusal an operator will read.

    From data, like every other operator sentence. Three earlier versions
    of this file spelled these out as literals, which is how the same
    sentence ended up written four times in one file and differently from
    the world model's.
    """
    words = (yaml.safe_load(Path(path).read_text()) or {}).get("refusals", {})
    return words.get(key, "")


def _token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail=_refusal("not_signed_in"))
    return authorization.split(" ", 1)[1]


def create_app(
    gateway: Gateway | None = None,
    track_url: str = DEFAULT_TRACK,
    character: str = "ops",
    speak_replies: bool = True,
    world_client=None,
) -> FastAPI:
    app = FastAPI(title="ARGUS voice")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.gateway = gateway or Gateway()
    # Readbacks proposed on one request and answered on the next, so the
    # store belongs to the process rather than to a request-scoped
    # service. Keys are namespaced per caller inside VoiceService.
    app.state.pending = {}
    app.state.track_url = track_url
    app.state.character_name = character
    app.state.speak = speak_replies
    # An injected client lets a test point this service at a world model
    # in the same process. The path is unchanged: same interfaces, same
    # token, same refusals.
    app.state.world_client = world_client

    def _service(authorization: str | None) -> VoiceService:
        token = _token(authorization)
        return VoiceService(
            gateway=app.state.gateway,
            world=WorldModel(
                base_url=app.state.track_url,
                token=token,
                client=app.state.world_client,
            ),
            character=load_character(app.state.character_name),
            speak_replies=app.state.speak,
            pending=app.state.pending,
            # Namespaces this caller's pending readbacks. Hashed rather
            # than stored, so a memory dump does not hand over a
            # credential.
            caller=hashlib.sha256(token.encode()).hexdigest()[:16],
        )

    @app.on_event("startup")
    async def _startup() -> None:
        # Says at boot what it can and cannot do, rather than discovering
        # it the first time an operator holds the button down.
        report = app.state.gateway.check()
        log.info("voice service ready on profile %r", report["profile"])

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "character": app.state.character_name,
            "characters": available_characters(),
        }

    @app.get("/v1/voice/capabilities")
    async def capabilities(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        """What this deployment's voice can actually do.

        C2 reads this to decide whether to offer the button at all, so an
        operator is never given a control that cannot work.

        Authenticated, because answering it runs every adapter's
        availability check, and one of those makes an outbound request.
        An unauthenticated caller must not be able to reach the gateway
        at all, however cheaply.
        """
        _token(authorization)
        # Off the event loop: an adapter's check can block on a socket
        # with a timeout, which would stall every other operator.
        report = await asyncio.to_thread(app.state.gateway.check)
        usable = {
            name: any(entry["usable"] for entry in entries)
            for name, entries in report["capabilities"].items()
        }
        return {
            "can_hear": usable.get("transcribe", False),
            "can_speak": usable.get("speak", False),
            "can_understand": usable.get("understand_order", False),
            "character": app.state.character_name,
        }

    async def _signed_in(service) -> bool:
        """Check the credential before anything expensive or outbound.

        The header shape is not a credential. Without this, any string
        beginning with "Bearer " reached the gateway, which under a bench
        profile means an unauthenticated caller could spend an API budget
        and be spoken to.

        One small read rather than a full view, so an exchange still costs
        the world model one picture of the world and not two.
        """
        try:
            await service.world.check_credentials()
        except NotSignedIn as exc:
            raise HTTPException(status_code=401, detail=_refusal("not_signed_in")) from exc
        except NotAllowed as exc:
            raise HTTPException(status_code=403, detail=_refusal("not_allowed")) from exc
        except WorldUnavailable:
            # Unreachable is not unauthorised, so the operator is not told
            # their credentials are wrong. But the credential has not been
            # checked either, so nothing may reach the gateway: the reply
            # is composed here, in text, without hearing or speaking.
            return False
        return True

    @app.post("/v1/voice/listen")
    async def listen(
        request: Request,
        audio: UploadFile | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Push to talk. Audio in, an exchange out."""
        service = _service(authorization)
        if audio is None:
            raise HTTPException(status_code=400, detail=_refusal("no_audio"))
        if not await _signed_in(service):
            return _blind(service)
        data = await audio.read()
        fmt = (audio.filename or "clip.wav").rsplit(".", 1)[-1].lower()
        return _as_json(await service.listen(data, audio_format=fmt))

    @app.post("/v1/voice/say")
    async def say(
        body: dict[str, Any] = Body(...),
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """The same exchange, typed rather than spoken.

        Not a debugging shortcut: an operator in a silent environment, or
        one whose microphone has failed, still needs the voice layer, and
        the honesty law's requirement that everything spoken is printed
        works just as well in reverse.
        """
        heard = (body.get("text") or "").strip()
        if not heard:
            raise HTTPException(status_code=400, detail=_refusal("nothing_said"))
        service = _service(authorization)
        if not await _signed_in(service):
            return _blind(service)
        return _as_json(await service.interpret(heard))

    @app.post("/v1/voice/confirm")
    async def confirm(
        body: dict[str, Any] = Body(...),
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Answer a readback. The only path that acts."""
        exchange_id = body.get("exchange_id") or ""
        if not exchange_id:
            raise HTTPException(status_code=400, detail=_refusal("no_order_to_confirm"))
        service = _service(authorization)
        if not await _signed_in(service):
            return _blind(service)
        return _as_json(await service.confirm(exchange_id, bool(body.get("confirmed"))))

    return app


def _blind(service) -> dict[str, Any]:
    """The reply when the world model cannot be reached.

    Composed here rather than by the service, because the service would
    reach the gateway to speak it, and the credential that got us here has
    not been checked. Text only: the printed record is what the honesty
    law requires, and the audio was always the extra.
    """
    import uuid as _uuid

    from voice import intent as _intents

    return {
        "exchange_id": str(_uuid.uuid4()),
        "heard": "",
        "spoken": service.character.say("cannot_see"),
        "kind": _intents.KIND_UNCLEAR,
        "needs_confirmation": False,
        "action": None,
        "audio": None,
        "audio_format": "wav",
    }


def _as_json(exchange) -> dict[str, Any]:
    """An exchange, as C2 receives it.

    The text is always present and the audio may not be. That order is
    deliberate: the printed record is the thing the honesty law requires,
    and the audio is the convenience on top of it.
    """
    return {
        "exchange_id": exchange.exchange_id,
        "heard": exchange.heard,
        "spoken": exchange.spoken,
        "kind": exchange.kind,
        "needs_confirmation": exchange.needs_confirmation,
        "action": exchange.action,
        "audio": base64.b64encode(exchange.audio).decode() if exchange.audio else None,
        "audio_format": exchange.audio_format,
    }


app = create_app(
    track_url=os.getenv("TRACK_URL", DEFAULT_TRACK),
    character=os.getenv("ARGUS_CHARACTER", "ops"),
)


def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s %(message)s"
    )
    uvicorn.run(
        create_app(
            track_url=os.getenv("TRACK_URL", DEFAULT_TRACK),
            character=os.getenv("ARGUS_CHARACTER", "ops"),
        ),
        host="127.0.0.1",
        port=int(os.getenv("VOICE_PORT", "8300")),
    )


if __name__ == "__main__":
    main()
