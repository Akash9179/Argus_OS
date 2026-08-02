"""Live state fan-out.

Everything an application watches in real time, tracks moving, assets
changing state, new events, task progress, is published here as a small
JSON envelope. WebSocket clients receive exactly these envelopes.

Redis carries them so that a second server process (or a future second
station) sees the same stream. When Redis is not reachable the in-process
bus is used instead: a single server keeps working, which is the
disconnection law applied to our own infrastructure.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Protocol

log = logging.getLogger(__name__)

# Envelope kinds. Applications switch on these.
ASSET_UPDATED = "asset.updated"
# Live motion, sent at telemetry rate. Separate from asset.updated because
# heading and speed are transient: they belong on the wire and on the map,
# not in the durable asset record.
ASSET_TELEMETRY = "asset.telemetry"
TRACK_UPDATED = "track.updated"
TASK_UPDATED = "task.updated"
EVENT_CREATED = "event.created"
ZONE_UPDATED = "zone.updated"


def envelope(kind: str, data: dict) -> dict:
    return {"kind": kind, "data": data}


class LiveBus(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def publish(self, kind: str, data: dict) -> None: ...

    def subscribe(self) -> "Subscription": ...


class Subscription:
    """A single consumer's queue of live envelopes."""

    def __init__(self, bus: "MemoryLiveBus | RedisLiveBus", maxsize: int = 512):
        self._bus = bus
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=maxsize)

    async def __aenter__(self) -> "Subscription":
        return self

    async def __aexit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._bus.remove(self)

    async def stream(self) -> AsyncIterator[dict]:
        while True:
            yield await self.queue.get()


class MemoryLiveBus:
    """In-process fan-out. Always present, and the fallback when Redis is not."""

    def __init__(self):
        self._subscribers: list[Subscription] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def subscribe(self) -> Subscription:
        sub = Subscription(self)
        self._subscribers.append(sub)
        return sub

    def remove(self, sub: Subscription) -> None:
        if sub in self._subscribers:
            self._subscribers.remove(sub)

    async def publish(self, kind: str, data: dict) -> None:
        self._deliver(envelope(kind, data))

    def _deliver(self, message: dict) -> None:
        for sub in list(self._subscribers):
            try:
                sub.queue.put_nowait(message)
            except asyncio.QueueFull:
                # A client too slow to keep up loses the oldest update
                # rather than stalling the whole server.
                try:
                    sub.queue.get_nowait()
                    sub.queue.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    log.warning("dropping live update for a slow subscriber")


class RedisLiveBus(MemoryLiveBus):
    """Fan-out through Redis pub/sub, with local delivery as well."""

    def __init__(self, url: str, channel: str):
        super().__init__()
        self._url = url
        self._channel = channel
        self._redis = None
        self._pubsub = None
        self._reader: asyncio.Task | None = None
        self.connected = False

    async def start(self) -> None:
        import redis.asyncio as aioredis

        try:
            self._redis = aioredis.from_url(self._url, decode_responses=True)
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(self._channel)
            self._reader = asyncio.create_task(self._read_loop())
            self.connected = True
            log.info("live bus using redis at %s", self._url)
        except Exception as exc:
            self.connected = False
            log.warning("redis unavailable (%s); using the in-process live bus", exc)

    async def stop(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(self._channel)
                await self._pubsub.aclose()
            except Exception:  # pragma: no cover - shutdown is best effort
                pass
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:  # pragma: no cover
                pass

    async def publish(self, kind: str, data: dict) -> None:
        message = envelope(kind, data)
        if self.connected and self._redis is not None:
            try:
                await self._redis.publish(self._channel, json.dumps(message))
                return
            except Exception as exc:
                log.warning("redis publish failed (%s); delivering locally", exc)
                self.connected = False
        self._deliver(message)

    async def _read_loop(self) -> None:
        assert self._pubsub is not None
        async for raw in self._pubsub.listen():
            if raw.get("type") != "message":
                continue
            try:
                self._deliver(json.loads(raw["data"]))
            except (ValueError, TypeError):
                log.warning("ignoring malformed live message")
