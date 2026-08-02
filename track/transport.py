"""Transport binding for the LINK contract.

The contract itself is transport-agnostic: it assumes only eventual
delivery and possible disconnection. This module is the one place that
knows the version 1 reference binding, MQTT with protobuf payloads, so
swapping in mesh radio or satellite later means writing another Transport
and changing nothing else.

The topic scheme is documented in link/README.md and implemented here:
    {prefix}/{asset_id}/heartbeat     asset to platform
    {prefix}/{asset_id}/telemetry     asset to platform
    {prefix}/{asset_id}/observation   asset to platform
    {prefix}/{asset_id}/task_status   asset to platform
    {prefix}/{asset_id}/task          platform to asset
"""

from __future__ import annotations

import fnmatch
import logging
import threading
from typing import Callable, Protocol

log = logging.getLogger(__name__)

MessageHandler = Callable[[str, bytes], None]

# The four message kinds an asset sends upward, and the one it receives.
KIND_HEARTBEAT = "heartbeat"
KIND_TELEMETRY = "telemetry"
KIND_OBSERVATION = "observation"
KIND_TASK_STATUS = "task_status"
KIND_TASK = "task"

UPWARD_KINDS = (KIND_HEARTBEAT, KIND_TELEMETRY, KIND_OBSERVATION, KIND_TASK_STATUS)


class Topics:
    """Builds and parses topic strings for one deployment prefix."""

    def __init__(self, prefix: str):
        self.prefix = prefix

    def upward(self, asset_id: str, kind: str) -> str:
        return f"{self.prefix}/{asset_id}/{kind}"

    def task(self, asset_id: str) -> str:
        return f"{self.prefix}/{asset_id}/{KIND_TASK}"

    def any_asset(self, kind: str) -> str:
        return f"{self.prefix}/+/{kind}"

    def asset_id_of(self, topic: str) -> str:
        """The asset identifier embedded in a topic, or empty if malformed."""
        parts = topic.split("/")
        return parts[1] if len(parts) >= 3 else ""

    def kind_of(self, topic: str) -> str:
        parts = topic.split("/")
        return parts[2] if len(parts) >= 3 else ""


class Transport(Protocol):
    """What the world model needs from any comms binding."""

    def publish(self, topic: str, payload: bytes) -> None: ...

    def subscribe(self, topic_filter: str, handler: MessageHandler) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


def _matches(topic_filter: str, topic: str) -> bool:
    """MQTT wildcard matching for + (one level) and # (rest)."""
    if topic_filter.endswith("/#"):
        return topic.startswith(topic_filter[:-2])
    pattern = topic_filter.replace("+", "*")
    filter_parts = topic_filter.split("/")
    topic_parts = topic.split("/")
    if len(filter_parts) != len(topic_parts):
        return False
    return fnmatch.fnmatchcase(topic, pattern)


class MemoryTransport:
    """In-process transport used by tests and by the offline sim loop.

    Behaves like the real broker for topic matching and delivery order,
    without needing a broker running. Handlers are called on the caller's
    thread, exactly as paho calls them on its own.
    """

    def __init__(self):
        self._handlers: list[tuple[str, MessageHandler]] = []
        self._lock = threading.RLock()
        self.published: list[tuple[str, bytes]] = []

    def publish(self, topic: str, payload: bytes) -> None:
        with self._lock:
            self.published.append((topic, payload))
            targets = [h for f, h in self._handlers if _matches(f, topic)]
        for handler in targets:
            handler(topic, payload)

    def subscribe(self, topic_filter: str, handler: MessageHandler) -> None:
        with self._lock:
            self._handlers.append((topic_filter, handler))

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


class MqttTransport:
    """The version 1 reference binding: MQTT with protobuf payloads."""

    def __init__(self, host: str, port: int, client_id: str):
        import paho.mqtt.client as mqtt

        self._mqtt = mqtt
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._host = host
        self._port = port
        self._subscriptions: list[tuple[str, MessageHandler]] = []
        self._connected = threading.Event()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        log.info("connected to broker at %s:%s", self._host, self._port)
        # Re-subscribe on every connect, so a reconnection restores the
        # full subscription set without the caller doing anything.
        for topic_filter, _ in self._subscriptions:
            client.subscribe(topic_filter, qos=1)
        self._connected.set()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None) -> None:
        self._connected.clear()
        log.warning("disconnected from broker: %s", reason_code)

    def publish(self, topic: str, payload: bytes) -> None:
        self._client.publish(topic, payload, qos=1)

    def subscribe(self, topic_filter: str, handler: MessageHandler) -> None:
        self._subscriptions.append((topic_filter, handler))

        def _on_message(client, userdata, message) -> None:
            handler(message.topic, message.payload)

        self._client.message_callback_add(topic_filter, _on_message)
        if self._connected.is_set():
            self._client.subscribe(topic_filter, qos=1)

    def start(self) -> None:
        self._client.connect_async(self._host, self._port, keepalive=30)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:  # pragma: no cover - shutdown is best effort
            pass

    def wait_connected(self, timeout: float = 5.0) -> bool:
        return self._connected.wait(timeout)
