"""Assembling the world model server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from track import api
from track.config import Settings, settings as default_settings
from track.identity import TokenDirectory
from track.live import MemoryLiveBus, RedisLiveBus
from track.store import Store
from track.transport import MqttTransport, Transport
from track.worldmodel import WorldModel

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    transport: Transport | None = None,
    store: Store | None = None,
    bus: MemoryLiveBus | None = None,
    tokens: TokenDirectory | None = None,
) -> FastAPI:
    """Build the server. Every dependency can be replaced, which is how the
    tests run the whole stack without a broker or a database file."""
    cfg = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or Store(cfg.db_path)
        app.state.tokens = tokens or TokenDirectory.from_file(cfg.tokens_path)
        app.state.bus = bus or RedisLiveBus(cfg.redis_url, channel=f"{cfg.topic_prefix}.live")
        app.state.transport = transport or MqttTransport(
            cfg.mqtt_host, cfg.mqtt_port, client_id=f"{cfg.topic_prefix}-worldmodel"
        )

        await app.state.bus.start()
        app.state.world = WorldModel(
            store=app.state.store,
            settings=cfg,
            transport=app.state.transport,
            bus=app.state.bus,
        )
        # Names for the event feed. Naming people is the identity service's
        # job, so the event writer asks it rather than printing identifiers.
        app.state.world.events.bind_person_lookup(app.state.tokens.display_name)
        await app.state.world.start()
        log.info("world model server ready")
        try:
            yield
        finally:
            await app.state.world.stop()
            await app.state.bus.stop()
            app.state.store.close()

    app = FastAPI(title="World model", version="1.0.0", lifespan=lifespan)

    # The operator application is served from a different origin during
    # development. Deployed installations serve it from the same origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api.router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "link_version": cfg.link_version, "ontology_version": cfg.ontology_version}

    return app
