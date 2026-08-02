"""The vehicle side of the comms driver interface.

A machine reaches the platform through a comms driver: publish, subscribe,
and connection-state events. Version 1 ships MQTT. This is the same shape
the hardware abstraction layer's comms drivers take, so the simulated
vehicle exercises the real interface rather than a convenient shortcut.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol

log = logging.getLogger(__name__)

Handler = Callable[[str, bytes], None]


class VehicleLink(Protocol):
    """What a vehicle needs from any comms driver."""

    def publish(self, topic: str, payload: bytes) -> None: ...

    def subscribe(self, topic: str, handler: Handler) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    @property
    def connected(self) -> bool: ...


class MqttVehicleLink:
    """The version 1 comms driver: MQTT."""

    def __init__(self, host: str, port: int, client_id: str):
        import paho.mqtt.client as mqtt

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._host = host
        self._port = port
        self._subscriptions: list[str] = []
        self._up = threading.Event()
        self.on_connected: Callable[[], None] | None = None

    @property
    def connected(self) -> bool:
        return self._up.is_set()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        for topic in self._subscriptions:
            client.subscribe(topic, qos=1)
        self._up.set()
        log.info("link up")
        if self.on_connected:
            self.on_connected()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None) -> None:
        self._up.clear()
        log.warning("link down")

    def publish(self, topic: str, payload: bytes) -> None:
        self._client.publish(topic, payload, qos=1)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subscriptions.append(topic)

        def _on_message(client, userdata, message) -> None:
            handler(message.topic, message.payload)

        self._client.message_callback_add(topic, _on_message)
        if self.connected:
            self._client.subscribe(topic, qos=1)

    def start(self) -> None:
        self._client.connect_async(self._host, self._port, keepalive=15)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:  # pragma: no cover - shutdown is best effort
            pass


class DirectVehicleLink:
    """An in-process comms driver.

    Used to run a whole vehicle, server, and application loop inside one
    test with no broker. It wraps anything exposing publish and subscribe,
    which is how the test wires a vehicle straight to the server.
    """

    def __init__(self, bus):
        self._bus = bus
        self._up = False
        self.on_connected: Callable[[], None] | None = None

    @property
    def connected(self) -> bool:
        return self._up

    def publish(self, topic: str, payload: bytes) -> None:
        if self._up:
            self._bus.publish(topic, payload)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._bus.subscribe(topic, handler)

    def start(self) -> None:
        self._up = True
        if self.on_connected:
            self.on_connected()

    def stop(self) -> None:
        self._up = False

    def drop(self) -> None:
        """Simulate losing the link without stopping the vehicle."""
        self._up = False

    def restore(self) -> None:
        self._up = True
        if self.on_connected:
            self.on_connected()
