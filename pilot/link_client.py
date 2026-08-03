"""The edge runtime's LINK client.

The machine side of the contract: four messages up, one down, through
whatever comms driver the manifest named. This is a second implementation
of the same five messages the simulated vehicle speaks, and that is
deliberate. Two independent implementations of one contract is how the
contract stays a contract rather than becoming whatever one program does.

Nothing here knows what kind of machine it is running on, and nothing here
knows what a driver is made of. It takes a comms driver and sends bytes.

Registry mirroring, and why it travels here
-------------------------------------------
The registry law requires that what the HAL knows reaches the world model.
The contract is frozen at version 1 and has no message for it, and reopening
the contract for this would be the wrong trade. `Telemetry.payload` is the
contract's own extension point, documented as "open, per-manifest extras...
Receivers must preserve and pass through keys they do not recognize", so the
registry snapshot travels there under the key "registry".

It is sent when it changes and when the link returns, never on every
sample, so the wire stays quiet. This is a convention chosen here, not
something the plan specified; it is recorded as decision 8 in the plan's
open decisions so it is reviewed rather than inherited.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from typing import Any, Callable

from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Struct
from google.protobuf.timestamp_pb2 import Timestamp
from link.v1.messages_pb2 import (
    Heartbeat,
    ObservationReport,
    TaskAssignment,
    TaskStatusUpdate,
    Telemetry,
)
from link.v1.ontology_pb2 import Observation, Position

from pilot.hal.interfaces import CommsDriver

log = logging.getLogger(__name__)

LINK_VERSION = 1
ONTOLOGY_VERSION = 1

# How many observations to hold while the link is down. Oldest go first: a
# fresh picture matters more than a complete one, and a machine that fills
# its memory with history is a machine that stops seeing.
OFFLINE_QUEUE_LIMIT = 500


def timestamp_now() -> Timestamp:
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts


class LinkClient:
    """Speaks the five LINK messages through a comms driver."""

    def __init__(
        self,
        asset_id: str,
        comms: CommsDriver,
        topic_prefix: str,
        on_task: Callable[[TaskAssignment], None],
    ):
        self.asset_id = asset_id
        self.prefix = topic_prefix
        self._comms = comms
        self._on_task = on_task
        self._queue: deque[tuple[str, bytes]] = deque(maxlen=OFFLINE_QUEUE_LIMIT)
        self._lock = threading.Lock()

        # What the world model has been told about this machine's insides,
        # so the registry is sent on change rather than on every sample.
        self._registry_sent: str | None = None
        self._registry_pending: dict[str, Any] | None = None

        self._comms.subscribe(self._task_topic(), self._on_task_message)
        self._comms.on_connected = self._on_link_up

    # -- topics ------------------------------------------------------------

    def _topic(self, kind: str) -> str:
        return f"{self.prefix}/{self.asset_id}/{kind}"

    def _task_topic(self) -> str:
        return self._topic("task")

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._comms.start()

    def stop(self) -> None:
        self._comms.stop()

    @property
    def connected(self) -> bool:
        return self._comms.connected

    def _on_link_up(self) -> None:
        # Everything held goes out, and the world model is re-told what this
        # machine is made of, because it may have been restarted while the
        # machine was alone.
        self._registry_sent = None
        self.flush()

    # -- receiving ---------------------------------------------------------

    def _on_task_message(self, topic: str, payload: bytes) -> None:
        try:
            assignment = TaskAssignment.FromString(payload)
        except Exception:
            log.exception("%s: could not read an order", self.asset_id)
            return
        # An order addressed to another machine is ignored even if it
        # arrives here.
        if assignment.task.asset_id and assignment.task.asset_id != self.asset_id:
            return
        self._on_task(assignment)

    # -- sending -----------------------------------------------------------

    def _send(self, kind: str, payload: bytes, hold_if_down: bool = False) -> None:
        if not self._comms.connected:
            if hold_if_down:
                with self._lock:
                    self._queue.append((kind, payload))
            return
        self._comms.publish(self._topic(kind), payload)

    def flush(self) -> None:
        """Send everything held while the link was down."""
        with self._lock:
            held, self._queue = list(self._queue), deque(maxlen=OFFLINE_QUEUE_LIMIT)
        for kind, payload in held:
            self._comms.publish(self._topic(kind), payload)
        if held:
            log.info("%s: sent %d held observations", self.asset_id, len(held))

    @property
    def held(self) -> int:
        with self._lock:
            return len(self._queue)

    # -- the registry ------------------------------------------------------

    def offer_registry(self, snapshot: dict[str, Any]) -> None:
        """Tell the client what the HAL currently knows.

        Called every loop. Only a change reaches the wire, and it rides the
        next telemetry sample rather than generating traffic of its own.
        """
        fingerprint = json.dumps(snapshot, sort_keys=True, default=str)
        if fingerprint == self._registry_sent:
            return
        self._registry_pending = snapshot
        self._registry_sent = fingerprint

    # -- the five messages -------------------------------------------------

    def heartbeat(
        self,
        asset_class: str,
        status: int,
        battery_fraction: float | None,
        position: Position,
        current_task_id: str,
    ) -> None:
        hb = Heartbeat(
            link_version=LINK_VERSION,
            ontology_version=ONTOLOGY_VERSION,
            asset_id=self.asset_id,
            asset_class=asset_class,
            status=status,
            position=position,
            current_task_id=current_task_id,
            timestamp=timestamp_now(),
        )
        if battery_fraction is not None:
            hb.battery_fraction = battery_fraction
        self._send("heartbeat", hb.SerializeToString())

    def telemetry(self, position: Position, heading_deg: float, speed_mps: float) -> None:
        msg = Telemetry(
            link_version=LINK_VERSION,
            ontology_version=ONTOLOGY_VERSION,
            asset_id=self.asset_id,
            position=position,
            heading_deg=heading_deg,
            speed_mps=speed_mps,
            timestamp=timestamp_now(),
        )
        pending = self._registry_pending
        if pending is not None:
            payload = Struct()
            ParseDict({"registry": _jsonable(pending)}, payload)
            msg.payload.CopyFrom(payload)
            # Only cleared once it is actually on the wire, so a snapshot
            # composed while the link was down is not lost.
            if self._comms.connected:
                self._registry_pending = None
        self._send("telemetry", msg.SerializeToString())

    def observation(self, observation: Observation) -> None:
        report = ObservationReport(
            link_version=LINK_VERSION,
            ontology_version=ONTOLOGY_VERSION,
            observation=observation,
        )
        # Observations are the one message worth holding through an outage:
        # heartbeats and telemetry describe now, while an observation
        # describes something that happened and would otherwise be lost.
        self._send("observation", report.SerializeToString(), hold_if_down=True)

    def task_status(
        self,
        task_id: str,
        status: int,
        progress: float,
        message: str,
        eta_sec: int | None = None,
    ) -> None:
        update = TaskStatusUpdate(
            link_version=LINK_VERSION,
            ontology_version=ONTOLOGY_VERSION,
            task_id=task_id,
            status=status,
            progress=progress,
            message=message,
            timestamp=timestamp_now(),
        )
        if eta_sec is not None:
            update.eta_sec = eta_sec
        self._send("task_status", update.SerializeToString())


def _jsonable(value: Any) -> Any:
    """Struct carries strings, numbers, booleans, lists and maps only."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return str(value)
