"""The world model: one live, shared picture of everything known.

This is where LINK messages become state. Every asset writes here through
the transport; every application reads here through the service interfaces.

Threading: the transport calls its handlers on its own thread, and those
handlers do nothing but hand the bytes to the event loop. All world model
work happens on the event loop, single threaded, so ordering is
deterministic and the store is never touched from two places at once.

Nothing in this module knows what kind of machine sent a message. Asset
class is carried, stored, and displayed, but never branched on: a drone and
a ground vehicle travel exactly the same path through this code.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from link.v1.messages_pb2 import (
    Heartbeat,
    ObservationReport,
    TaskAssignment,
    TaskStatusUpdate,
    Telemetry,
)
from link.v1.ontology_pb2 import (
    Asset,
    AssetStatus,
    Issuer,
    Relationship,
    Task,
    TaskParameters,
    TaskState,
    TaskStateChange,
    Track,
    TrackState,
)

from track import live
from track.codec import asset_to_dict, task_to_dict, to_dict
from track.config import Settings
from track.events import EventWriter, Language
from track.fusion import TrackManager
from track.ids import epoch_now, new_id, now_ts, to_epoch
from track.store import Event, Store
from track.transport import UPWARD_KINDS, Topics, Transport
from track.zones import ZoneEvaluator

log = logging.getLogger(__name__)

# Task states in which an order is still the asset's responsibility.
OPEN_TASK_STATES = (
    TaskState.TASK_STATE_PENDING,
    TaskState.TASK_STATE_ACCEPTED,
    TaskState.TASK_STATE_RUNNING,
)


class TaskRejected(Exception):
    """An order could not be created. The message is operator-facing."""


@dataclass
class LatestTelemetry:
    """The most recent motion sample for an asset.

    Heading and speed are live motion, not durable asset state, so they are
    kept here and streamed rather than written into the asset record.
    """

    asset_id: str
    latitude_deg: float
    longitude_deg: float
    heading_deg: float
    speed_mps: float
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "asset_id": self.asset_id,
            "position": {"latitude_deg": self.latitude_deg, "longitude_deg": self.longitude_deg},
            "heading_deg": self.heading_deg,
            "speed_mps": self.speed_mps,
            "timestamp": self.timestamp,
        }


class WorldModel:
    """Ingest, fusion, registry, tasking, and the event feed."""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        transport: Transport,
        bus: live.MemoryLiveBus,
        language: Language | None = None,
    ):
        self.store = store
        self.settings = settings
        self.transport = transport
        self.bus = bus
        self.topics = Topics(settings.topic_prefix)
        self.tracks = TrackManager(store, settings)
        self.zone_eval = ZoneEvaluator(store)

        self.language = language or Language.from_file(settings.event_templates_path)
        self.events = EventWriter(self.language)
        self.events.bind_asset_lookup(store.get_asset)

        self.telemetry: dict[str, LatestTelemetry] = {}

        self._inbox: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(maxsize=4096)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task] = []

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        for kind in UPWARD_KINDS:
            self.transport.subscribe(self.topics.any_asset(kind), self._on_transport_message)
        self.transport.start()
        self._tasks = [
            asyncio.create_task(self._drain_inbox(), name="worldmodel-inbox"),
            asyncio.create_task(self._watchdog(), name="worldmodel-watchdog"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self.transport.stop()

    # -- transport handoff -------------------------------------------------

    def _on_transport_message(self, topic: str, payload: bytes) -> None:
        """Called on the transport's thread. Hands off and returns at once."""
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._inbox.put_nowait, (topic, payload))
        except (RuntimeError, asyncio.QueueFull):
            log.warning("dropping a message from %s: server is not keeping up", topic)

    async def _drain_inbox(self) -> None:
        while True:
            topic, payload = await self._inbox.get()
            try:
                await self.handle(topic, payload)
            except Exception:
                log.exception("failed to handle a message from %s", topic)

    async def handle(self, topic: str, payload: bytes) -> None:
        """Route one wire message by its topic."""
        kind = self.topics.kind_of(topic)
        if kind == "heartbeat":
            await self.on_heartbeat(Heartbeat.FromString(payload))
        elif kind == "telemetry":
            await self.on_telemetry(Telemetry.FromString(payload))
        elif kind == "observation":
            await self.on_observation(ObservationReport.FromString(payload))
        elif kind == "task_status":
            await self.on_task_status(TaskStatusUpdate.FromString(payload))
        else:
            log.warning("ignoring a message on an unrecognised topic: %s", topic)

    # -- inbound messages --------------------------------------------------

    async def on_heartbeat(self, hb: Heartbeat) -> None:
        self._check_versions(hb.link_version, hb.ontology_version, hb.asset_id)

        asset = self.store.get_asset(hb.asset_id) or Asset(asset_id=hb.asset_id)
        previous_status = asset.status

        asset.asset_class = hb.asset_class
        asset.status = hb.status
        if hb.HasField("battery_fraction"):
            asset.battery_fraction = hb.battery_fraction
        asset.position.CopyFrom(hb.position)
        asset.current_task_id = hb.current_task_id
        # Liveness is measured by when we heard, not by the asset's clock,
        # so a machine with a wrong clock is not wrongly declared offline.
        asset.last_heartbeat.CopyFrom(now_ts())
        self.store.put_asset(asset)

        came_back = previous_status in (
            AssetStatus.ASSET_STATUS_UNSPECIFIED,
            AssetStatus.ASSET_STATUS_OFFLINE,
        )
        if came_back and asset.status != AssetStatus.ASSET_STATUS_OFFLINE:
            await self._emit(self.events.asset_online(asset))
        elif asset.status == AssetStatus.ASSET_STATUS_FAULT and previous_status != asset.status:
            await self._emit(self.events.asset_fault(asset))

        await self.bus.publish(live.ASSET_UPDATED, asset_to_dict(asset, self.language.asset_name(asset)))

    async def on_telemetry(self, msg: Telemetry) -> None:
        self._check_versions(msg.link_version, msg.ontology_version, msg.asset_id)

        asset = self.store.get_asset(msg.asset_id) or Asset(asset_id=msg.asset_id)
        asset.position.CopyFrom(msg.position)
        self.store.put_asset(asset)

        sample = LatestTelemetry(
            asset_id=msg.asset_id,
            latitude_deg=msg.position.latitude_deg,
            longitude_deg=msg.position.longitude_deg,
            heading_deg=msg.heading_deg,
            speed_mps=msg.speed_mps,
            timestamp=to_epoch(msg.timestamp) or epoch_now(),
        )
        self.telemetry[msg.asset_id] = sample
        await self.bus.publish(live.ASSET_TELEMETRY, sample.to_dict())

    async def on_observation(self, report: ObservationReport) -> None:
        obs = report.observation
        self._check_versions(report.link_version, report.ontology_version, obs.asset_id)

        result = self.tracks.ingest(obs)
        track = result.track

        transition = self.zone_eval.evaluate(track)
        if transition.threat_level is not None and transition.threat_level > track.threat_level:
            track.threat_level = transition.threat_level
            self.store.put_track(track)

        if result.created_track:
            place = self.zone_eval.place_name(track.position)
            await self._emit(self.events.track_created(track, result.entity, obs, place))

        for zone in transition.alert_on_entered:
            await self._emit(self.events.zone_entry(track, result.entity, zone))
        for zone in transition.entered:
            # The graph remembers where things went, whether or not the zone
            # was configured to raise an alert.
            self.store.put_relationship(
                Relationship(
                    relationship_id=new_id(),
                    subject_id=track.entity_id,
                    predicate="inside",
                    object_id=zone.zone_id,
                    confidence=track.confidence,
                    timestamp=now_ts(),
                )
            )
        for zone in transition.alert_on_exited:
            await self._emit(self.events.zone_exit(track, result.entity, zone))

        await self.bus.publish(live.TRACK_UPDATED, to_dict(track))

    async def on_task_status(self, update: TaskStatusUpdate) -> None:
        task = self.store.get_task(update.task_id)
        if task is None:
            log.warning("status for an order we do not have: %s", update.task_id)
            return

        previous = task.status
        task.status = update.status
        task.status_history.append(
            TaskStateChange(
                state=update.status,
                timestamp=update.timestamp if update.HasField("timestamp") else now_ts(),
                message=update.message,
            )
        )
        self.store.put_task(task)

        if update.status != previous:
            kind = {
                TaskState.TASK_STATE_ACCEPTED: "task_accepted",
                TaskState.TASK_STATE_DONE: "task_done",
                TaskState.TASK_STATE_FAILED: "task_failed",
                TaskState.TASK_STATE_CANCELLED: "task_cancelled",
            }.get(update.status)
            if kind:
                asset = self.store.get_asset(task.asset_id)
                await self._emit(self.events.task_event(kind, task, asset, update.message))

        await self.bus.publish(
            live.TASK_UPDATED,
            {
                "task": task_to_dict(task, self.language.task_phrase(task.task_type)),
                "progress": update.progress,
                "eta_sec": update.eta_sec if update.HasField("eta_sec") else None,
                "message": update.message,
            },
        )

    # -- outbound orders ---------------------------------------------------

    async def issue_task(
        self,
        asset_id: str,
        task_type: str,
        parameters: TaskParameters,
        issuer: Issuer,
        priority: int = 0,
    ) -> Task:
        """Create an order, persist it, and send it to the asset.

        Every order, whether it came from the map, from voice, or from
        another system, passes through here. There is no second path.
        """
        asset = self.store.get_asset(asset_id)
        if asset is None:
            raise TaskRejected(self.language.error("no_such_asset"))
        if asset.status == AssetStatus.ASSET_STATUS_OFFLINE:
            raise TaskRejected(
                self.language.error("asset_not_answering", asset=self.language.asset_name(asset))
            )

        task = Task(
            task_id=new_id(),
            asset_id=asset_id,
            task_type=task_type,
            parameters=parameters,
            priority=priority,
            status=TaskState.TASK_STATE_PENDING,
            issued_by=issuer,
        )
        task.status_history.append(
            TaskStateChange(state=TaskState.TASK_STATE_PENDING, timestamp=now_ts())
        )
        self.store.put_task(task)

        self._send_task(task)
        await self._emit(self.events.task_event("task_issued", task, asset))
        await self.bus.publish(live.TASK_UPDATED, {"task": task_to_dict(task, self.language.task_phrase(task.task_type)), "progress": 0.0})
        return task

    async def cancel_task(self, task_id: str) -> Task:
        """Cancel an order and tell the asset.

        Cancellation reuses the TASK message with the task's status set to
        cancelled. The contract has no separate cancel message, and adding
        one would be a version bump.
        """
        task = self.store.get_task(task_id)
        if task is None:
            raise TaskRejected(self.language.error("no_such_task"))
        if task.status not in OPEN_TASK_STATES:
            raise TaskRejected(self.language.error("task_already_finished"))

        task.status = TaskState.TASK_STATE_CANCELLED
        task.status_history.append(
            TaskStateChange(state=TaskState.TASK_STATE_CANCELLED, timestamp=now_ts())
        )
        self.store.put_task(task)

        self._send_task(task)
        await self._emit(
            self.events.task_event("task_cancelled", task, self.store.get_asset(task.asset_id))
        )
        await self.bus.publish(live.TASK_UPDATED, {"task": task_to_dict(task, self.language.task_phrase(task.task_type)), "progress": 0.0})
        return task

    def _send_task(self, task: Task) -> None:
        assignment = TaskAssignment(
            link_version=self.settings.link_version,
            ontology_version=self.settings.ontology_version,
            task=task,
            timestamp=now_ts(),
        )
        self.transport.publish(self.topics.task(task.asset_id), assignment.SerializeToString())

    # -- the watchdog ------------------------------------------------------

    async def _watchdog(self) -> None:
        while True:
            try:
                await self.watchdog_tick()
            except Exception:
                log.exception("watchdog tick failed")
            await asyncio.sleep(self.settings.watchdog_interval_s)

    async def watchdog_tick(self) -> None:
        """Age out silent assets, unacknowledged orders, and stale tracks."""
        now = epoch_now()

        for asset in self.store.list_assets():
            if asset.status == AssetStatus.ASSET_STATUS_OFFLINE:
                continue
            heard = to_epoch(asset.last_heartbeat)
            if not heard or now - heard <= self.settings.heartbeat_timeout_s:
                continue

            asset.status = AssetStatus.ASSET_STATUS_OFFLINE
            self.store.put_asset(asset)
            await self._emit(self.events.asset_offline(asset))
            await self.bus.publish(live.ASSET_UPDATED, asset_to_dict(asset, self.language.asset_name(asset)))
            await self._fail_open_tasks(asset, self.language.fragment("reason_asset_silent"))

        for task in self.store.list_tasks_in_states([TaskState.TASK_STATE_PENDING]):
            issued = to_epoch(task.status_history[0].timestamp) if task.status_history else 0.0
            if issued and now - issued > self.settings.task_ack_timeout_s:
                await self._fail_task(task, self.language.fragment("reason_no_acknowledgement"))

        for track in self.tracks.sweep():
            if track.state == TrackState.TRACK_STATE_LOST:
                entity = self.store.get_entity(track.entity_id)
                if entity is not None:
                    place = self.zone_eval.place_name(track.position)
                    await self._emit(self.events.track_lost(track, entity, place))
            await self.bus.publish(live.TRACK_UPDATED, to_dict(track))

    async def _fail_open_tasks(self, asset: Asset, reason: str) -> None:
        for task in self.store.list_tasks(asset_id=asset.asset_id):
            if task.status in OPEN_TASK_STATES:
                await self._fail_task(task, reason)

    async def _fail_task(self, task: Task, reason: str) -> None:
        task.status = TaskState.TASK_STATE_FAILED
        task.status_history.append(
            TaskStateChange(state=TaskState.TASK_STATE_FAILED, timestamp=now_ts(), message=reason)
        )
        self.store.put_task(task)
        await self._emit(
            self.events.task_event("task_failed", task, self.store.get_asset(task.asset_id), reason)
        )
        await self.bus.publish(live.TASK_UPDATED, {"task": task_to_dict(task, self.language.task_phrase(task.task_type)), "progress": 0.0})

    # -- helpers -----------------------------------------------------------

    async def _emit(self, event: Event) -> None:
        self.store.put_event(event)
        await self.bus.publish(live.EVENT_CREATED, event.to_dict())

    def _check_versions(self, link_version: int, ontology_version: int, asset_id: str) -> None:
        """Warn on a version mismatch, but never drop the message.

        A newer asset is still worth listening to: protobuf keeps what this
        build does not understand, and refusing the message would lose data
        the operator may need.
        """
        if link_version and link_version != self.settings.link_version:
            log.warning(
                "asset %s speaks contract version %s, this server speaks %s",
                asset_id,
                link_version,
                self.settings.link_version,
            )
        if ontology_version and ontology_version != self.settings.ontology_version:
            log.warning(
                "asset %s speaks ontology version %s, this server speaks %s",
                asset_id,
                ontology_version,
                self.settings.ontology_version,
            )
