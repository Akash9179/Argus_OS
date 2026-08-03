"""The version 1 comms driver: MQTT over WiFi.

Real, and needing no hardware beyond a network, which is why it ships in
Stage 3A rather than waiting for the machine. Mesh radio and satellite are
later drivers behind the same interface, and adding one must not touch the
LINK client or the autonomy core.

Reconnection is the driver's business, not the runtime's. The autonomy core
never asks whether the link is up before deciding to keep working, because
under the disconnection law the answer would not change what it does.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from pilot.hal.interfaces import DriverHealth, DriverInfo, Handler
from pilot.hal.language import say
from pilot.hal.loader import register_driver
from pilot.hal.manifest import Manifest
from pilot.hal.registry import Device

log = logging.getLogger(__name__)

DRIVER_VERSION = "1.0.0"


class MqttComms:
    """Publish, subscribe, and connection state, over MQTT."""

    def __init__(
        self,
        manifest: Manifest,
        host: str = "127.0.0.1",
        port: int = 1883,
        keepalive_s: int = 15,
        **_ignored: Any,
    ):
        import paho.mqtt.client as mqtt

        self._host = str(host)
        self._port = int(port)
        self._keepalive = int(keepalive_s)
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"pilot-{manifest.asset_id}"
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._subscriptions: list[str] = []
        self._up = threading.Event()
        self._ever_connected = False
        self.on_connected: Callable[[], None] | None = None

    def info(self) -> DriverInfo:
        return DriverInfo(
            name="mqtt_comms",
            kind="comms",
            version=DRIVER_VERSION,
            device="network",
            settings={"host": self._host, "port": str(self._port)},
        )

    def health(self) -> DriverHealth:
        # Being disconnected is not a fault: the machine is designed to work
        # alone. Never having connected at all is worth saying out loud,
        # because it usually means the address is wrong.
        where = f"{self._host}:{self._port}"
        if self._up.is_set():
            return DriverHealth(True, say("link_up_to", host=where))
        if self._ever_connected:
            return DriverHealth(True, say("link_down"))
        return DriverHealth(True, say("link_never", host=where))

    def scan(self) -> list[Device]:
        return [
            Device(
                bus="network",
                identifier=f"{self._host}:{self._port}",
                description="MQTT broker",
                present=self._up.is_set(),
            )
        ]

    @property
    def connected(self) -> bool:
        return self._up.is_set()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        for topic in self._subscriptions:
            client.subscribe(topic, qos=1)
        self._up.set()
        self._ever_connected = True
        log.info("link up")
        if self.on_connected:
            self.on_connected()

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties=None
    ) -> None:
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
        self._client.connect_async(self._host, self._port, keepalive=self._keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:  # pragma: no cover - shutdown is best effort
            pass


register_driver("mqtt_comms", MqttComms)
