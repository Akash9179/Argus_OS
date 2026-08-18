"""A LINK client, as a machine implements it.

This is the vehicle side of the contract: it builds the four upward
messages, listens for orders on the one downward topic, and holds what it
cannot send while disconnected. The real runtime implements the same five
messages against the same topic scheme; this is the reference for what that
looks like.

Connectivity adds capability and never enables it. With the link down the
vehicle keeps working and keeps its observations, then sends them when the
link returns.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable

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

from sim.transport import VehicleLink

log = logging.getLogger(__name__)

LINK_VERSION = 1
ONTOLOGY_VERSION = 1

# How many observations to hold while the link is down. The oldest are
# dropped first: a fresh picture matters more than a complete one.
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
        link: VehicleLink,
        topic_prefix: str,
        on_task: Callable[[TaskAssignment], None],
    ):
        self.asset_id = asset_id
        self.prefix = topic_prefix
        self._link = link
        self._on_task = on_task
        self._queue: deque[tuple[str, bytes]] = deque(maxlen=OFFLINE_QUEUE_LIMIT)
        self._lock = threading.Lock()
        # The machine's capability declaration, kept so every reconnect
        # can repeat it (link/CONVENTIONS.md section 1). Re-declaring is
        # idempotent on the platform side, which merges.
        self._declaration: bytes | None = None

        self._link.subscribe(self._task_topic(), self._on_task_message)
        # Whatever was held during an outage goes out as soon as the link
        # comes back, without the vehicle having to notice.
        if hasattr(self._link, "on_connected"):
            self._link.on_connected = self.flush

    # -- topics ------------------------------------------------------------

    def _topic(self, kind: str) -> str:
        return f"{self.prefix}/{self.asset_id}/{kind}"

    def _task_topic(self) -> str:
        return self._topic("task")

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._link.start()

    def stop(self) -> None:
        self._link.stop()

    @property
    def connected(self) -> bool:
        return self._link.connected

    # -- receiving ---------------------------------------------------------

    def _on_task_message(self, topic: str, payload: bytes) -> None:
        try:
            assignment = TaskAssignment.FromString(payload)
        except Exception:
            log.exception("%s: could not read an order", self.asset_id)
            return
        # Orders addressed to another machine are ignored even if they
        # arrive here.
        if assignment.task.asset_id and assignment.task.asset_id != self.asset_id:
            return
        self._on_task(assignment)

    # -- sending -----------------------------------------------------------

    def _send(self, kind: str, payload: bytes, hold_if_down: bool = False) -> None:
        if not self._link.connected:
            if hold_if_down:
                with self._lock:
                    self._queue.append((kind, payload))
            return
        self._link.publish(self._topic(kind), payload)

    def flush(self) -> None:
        """Send everything held while the link was down, and re-declare."""
        with self._lock:
            held, self._queue = list(self._queue), deque(maxlen=OFFLINE_QUEUE_LIMIT)
            declaration = self._declaration
        if declaration is not None:
            self._link.publish(self._topic("telemetry"), declaration)
        for kind, payload in held:
            self._link.publish(self._topic(kind), payload)
        if held:
            log.info("%s: sent %d held messages", self.asset_id, len(held))

    @property
    def held(self) -> int:
        with self._lock:
            return len(self._queue)

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

    def telemetry(
        self,
        position: Position,
        heading_deg: float,
        speed_mps: float,
        payload: dict | None = None,
    ) -> None:
        msg = Telemetry(
            link_version=LINK_VERSION,
            ontology_version=ONTOLOGY_VERSION,
            asset_id=self.asset_id,
            position=position,
            heading_deg=heading_deg,
            speed_mps=speed_mps,
            timestamp=timestamp_now(),
        )
        if payload is not None:
            # The contract's documented extension point (D-8): open data
            # rides Telemetry.payload rather than reopening frozen v1.
            struct = Struct()
            ParseDict(payload, struct)
            msg.payload.CopyFrom(struct)
            # A telemetry carrying a payload is a declaration, not a
            # position sample: stale coordinates are worthless a second
            # later, but a declaration the platform never received stays
            # missing forever. It is remembered and re-sent on every
            # connect (the convention says on change and after a
            # reconnect), rather than riding the capped outage queue
            # where enough observations could evict it.
            self._declaration = msg.SerializeToString()
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
