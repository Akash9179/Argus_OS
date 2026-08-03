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
from datetime import datetime, timezone

from google.protobuf.json_format import MessageToDict
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

from track import geo, live
from track.codec import (
    asset_to_dict,
    task_to_dict,
    tasks_to_dicts,
    to_dict,
    track_to_dict,
    tracks_to_dicts,
)
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


# The autonomy modes this build actually enforces, named by the code that
# enforces them. The language file supplies their words; it cannot invent a
# mode, because a mode nothing acts on is a setting an operator can select
# and the platform will silently ignore. Adding one means writing the
# behaviour here first.
ENFORCED_AUTONOMY_MODES = ("manual", "automatic")


def check_autonomy_language(language: Language) -> None:
    """Refuse a language file that promises a mode nothing implements.

    At startup, loudly, for the same reason a misspelled AI policy profile
    is refused rather than defaulted: the failure has to happen where
    somebody is looking, not on the first operator who selects the mode.
    """
    listed = set(language.autonomy_modes)
    unenforceable = listed - set(ENFORCED_AUTONOMY_MODES)
    if unenforceable:
        raise ValueError(
            f"the language file lists autonomy modes nothing enforces: "
            f"{', '.join(sorted(unenforceable))}. Implement the behaviour "
            f"before offering the setting."
        )
    if language.default_autonomy_mode not in listed:
        raise ValueError(
            f"the default autonomy mode {language.default_autonomy_mode!r} is not one "
            f"of the modes offered"
        )
    for mode in listed:
        # Every mode needs its own sentence and its own colour. Without the
        # sentence, switching raises after the change is already written;
        # without the colour it falls back to routine, and a mode that lets
        # the platform act unasked is not routine.
        try:
            language.template(f"autonomy_{mode}")
        except KeyError:
            raise ValueError(
                f"the autonomy mode {mode!r} has no sentence in the language file"
            ) from None
        if f"autonomy_{mode}" not in language.severities:
            raise ValueError(
                f"the autonomy mode {mode!r} has no colour in the language file, so it "
                f"would read as routine"
            )


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
        check_autonomy_language(self.language)
        self.events = EventWriter(self.language)
        self.events.bind_asset_lookup(store.get_asset)

        self.telemetry: dict[str, LatestTelemetry] = {}

        self._inbox: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(maxsize=4096)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task] = []

    # -- how applications see a contact -------------------------------------

    def track_class(self, track: Track) -> str:
        """The class of the thing a track is following, or nothing.

        A track whose entity has gone is not an error. The naming falls back
        to the unknown label, which is a word rather than a blank.
        """
        entity = self.store.get_entity(track.entity_id) if track.entity_id else None
        return entity.entity_class if entity is not None else ""

    def track_view(self, track: Track) -> dict:
        """One contact, named and placed, exactly as the stream serves it."""
        return track_to_dict(
            track,
            self.language.track_name(self.track_class(track), track.confidence),
            self.language.place_phrase(self.zone_eval.place_name(track.position)),
        )

    def track_views(self, tracks) -> list[dict]:
        return tracks_to_dicts(
            tracks, self.language, self.track_class, self.zone_eval.place_name
        )

    # -- autonomy: what this platform may do unasked -------------------------

    def autonomy_of(self, asset_id: str) -> str:
        """How much this platform may do with a machine without being asked.

        A machine nobody has decided about is manual. The default is not a
        convenience: a machine that acts on its own because no row existed
        would be the platform taking an action nobody chose.
        """
        return self.store.get_autonomy(asset_id) or self.language.default_autonomy_mode

    def asset_view(self, asset: Asset) -> dict:
        """An asset as applications see it, carrying its resolved mode.

        Annotated here for the same reason the name is: an application that
        had to work out the mode for itself would be a second authority on
        a question only the platform can answer, since only the platform
        enforces it.
        """
        view = asset_to_dict(asset, self.language.asset_name(asset))
        view["autonomy"] = self.autonomy_of(asset.asset_id)
        return view

    def asset_views(self, assets) -> list[dict]:
        return [self.asset_view(a) for a in assets]

    async def set_autonomy(self, asset_id: str, mode: str, principal_id: str) -> dict:
        """Change how much this platform may do with a machine unasked.

        A mode this build cannot enforce is refused rather than stored. A
        setting the system cannot honour is not a setting, it is a false
        claim on an operator's screen, and the same reasoning refuses a
        misspelled AI policy profile at startup.
        """
        asset = self.store.get_asset(asset_id)
        if asset is None:
            raise TaskRejected(self.language.error("no_such_asset"))
        if not self.language.knows_autonomy_mode(mode):
            raise TaskRejected(
                self.language.error(
                    "no_such_autonomy_mode", choices=self.language.autonomy_choices()
                )
            )

        previous = self.autonomy_of(asset_id)
        self.store.set_autonomy(asset_id, mode, principal_id)

        if mode != previous:
            await self._emit(self.events.autonomy_changed(asset, mode, principal_id))

        view = self.asset_view(asset)
        await self.bus.publish(live.ASSET_UPDATED, view)

        # Acting on the new mode is the point of setting it. Going automatic
        # sweeps the contacts nobody has looked at; going manual withdraws
        # what this platform started and nothing else.
        if mode == "automatic" and previous != "automatic":
            await self.investigate_open_contacts()
        elif mode != "automatic" and previous == "automatic":
            await self.withdraw_own_orders(asset_id)
        return view

    # -- acting on the mode --------------------------------------------------

    def _eligible_for(self, track: Track) -> Asset | None:
        """The machine this platform should send to look, or none.

        Nearest wins. Which machine goes is the platform's call because only
        the platform holds the fused picture; a station's idea of "the
        selected machine" is a fact about a browser tab, not about the site.

        Eligible means: set to automatic, currently answering, and not
        already carrying an order. A machine that is busy is left alone
        rather than having its work replaced.
        """
        busy = {task.asset_id for task in self.store.list_tasks_in_states(OPEN_TASK_STATES)}
        candidates = []
        for asset in self.store.list_assets():
            if self.autonomy_of(asset.asset_id) != "automatic":
                continue
            if asset.status == AssetStatus.ASSET_STATUS_OFFLINE:
                continue
            if asset.asset_id in busy:
                continue
            if not asset.HasField("position"):
                continue
            if not self._can_be_told_to(asset, "navigate"):
                continue
            candidates.append(asset)
        if not candidates:
            return None
        return min(candidates, key=lambda a: geo.distance_m(a.position, track.position))

    @staticmethod
    def _can_be_told_to(asset: Asset, task_type: str) -> bool:
        """Does this machine say it can be told to do this?

        Read from what the machine declared, never from what kind of thing
        it is: branching on asset_class here would put vehicle specifics
        above the hardware abstraction layer. A machine that declares
        nothing is allowed through and refuses for itself, the same way the
        tasking endpoint does not police the vocabulary either.
        """
        if not asset.HasField("capabilities"):
            return True
        declared = asset.capabilities.fields.get("supported_task_types")
        if declared is None or not declared.HasField("string_value"):
            return True
        return task_type in [t.strip() for t in declared.string_value.split(",")]

    async def investigate(self, track: Track) -> Task | None:
        """Send a machine to look at a contact, if one should go.

        Every order goes through `issue_task`, the same single path a map
        click uses, carrying an issuer with no principal and the automatic
        channel. The existing machinery then names nobody on every surface:
        this platform ordered it, and no person did.
        """
        if self.store.was_investigated(track.track_id):
            return None
        asset = self._eligible_for(track)
        if asset is None:
            return None

        try:
            task = await self.issue_task(
                asset_id=asset.asset_id,
                task_type="navigate",
                parameters=TaskParameters(waypoints=[track.position]),
                issuer=Issuer(principal_id="", channel="automatic"),
            )
        except TaskRejected as refused:
            # The machine went quiet between the check and the order. Not
            # worth an operator's attention and never worth retrying into a
            # storm: the next contact will find another machine.
            log.info("no order issued for %s: %s", track.track_id, refused)
            return None

        self.store.record_investigation(track.track_id, task.task_id, asset.asset_id)
        return task

    async def investigate_open_contacts(self) -> None:
        """Look at everything nobody has looked at yet.

        Run when a machine is switched to automatic, so the setting takes
        effect on the contacts already on the map rather than only on the
        next one to appear.
        """
        # Everything not closed, and not merely a recent window: on a busy
        # site an older open contact would otherwise never be looked at.
        # Asked as "has this ended" rather than by listing live states, so a
        # track whose state was never set is examined rather than skipped.
        for track in self.store.list_tracks(limit=10_000):
            if track.state == TrackState.TRACK_STATE_CLOSED:
                continue
            await self.investigate(track)

    async def withdraw_own_orders(self, asset_id: str) -> None:
        """Cancel the orders this platform issued to a machine on its own.

        Only those. An operator's order, a voice order, or another system's
        order belongs to whoever gave it, and taking it back because a mode
        changed would be the platform acting on somebody else's behalf.
        """
        for task_id in self.store.investigation_tasks_for(asset_id):
            task = self.store.get_task(task_id)
            if task is None or task.status not in OPEN_TASK_STATES:
                continue
            try:
                await self.cancel_task(task_id)
            except TaskRejected as refused:
                log.info("could not withdraw %s: %s", task_id, refused)

    def task_view(self, task: Task) -> dict:
        """One order, in words: what was asked, who asked, and why.

        An order with no issuer on record names nobody. Saying "someone
        signed in" here would assert a person the record does not have, and
        would disagree with the event feed, which calls the same order the
        system's.
        """
        who = ""
        channel = ""
        if task.HasField("issued_by"):
            channel = task.issued_by.channel
            # A self-issued order names nobody, even though it was made on a
            # person's token. All three surfaces that can say who acted (this
            # field, the reason beside it, and the event feed's source line)
            # read the one list, so an application built on this later cannot
            # reintroduce the misattribution by picking a different field.
            if task.issued_by.principal_id and not self.language.is_self_issued(channel):
                who = self.events.name_person(task.issued_by.principal_id)
        return task_to_dict(
            task,
            self.language.task_phrase(task.task_type),
            who,
            self.language.task_reason(channel, who, self._issued_at(task)),
        )

    def _issued_at(self, task: Task) -> str:
        """The clock time an order was given, or nothing.

        The wording, including the Z, comes from the language file: this is
        a string an operator reads, and none of those are written in code.
        """
        if not task.status_history:
            return ""
        stamp = task.status_history[0].timestamp
        if not stamp.seconds:
            return ""
        return self.language.time_of_day(
            stamp.ToDatetime(), today=datetime.now(timezone.utc).date()
        )

    def task_views(self, tasks) -> list[dict]:
        return tasks_to_dicts(tasks, self.task_view)

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

        await self.bus.publish(live.ASSET_UPDATED, self.asset_view(asset))

    async def on_telemetry(self, msg: Telemetry) -> None:
        self._check_versions(msg.link_version, msg.ontology_version, msg.asset_id)

        asset = self.store.get_asset(msg.asset_id) or Asset(asset_id=msg.asset_id)
        asset.position.CopyFrom(msg.position)
        if msg.HasField("payload"):
            self._absorb_payload(asset, msg)
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

    def _absorb_payload(self, asset: Asset, msg: Telemetry) -> None:
        """Take in what a machine's hardware layer says it is made of.

        The contract is frozen at version 1 and has no message for a
        capability manifest or a driver registry. `Telemetry.payload` is the
        contract's own extension point for per-manifest extras, so machines
        send their registry there and it is absorbed here. Reopening the
        contract for this would have been the more expensive trade.

        Everything the machine sent is kept as it arrived, including keys
        this build does not recognise, for the same reason unknown protobuf
        fields are kept: an older server must not silently destroy a newer
        machine's data.
        """
        payload = MessageToDict(msg.payload)
        if not payload:
            return

        # The whole payload is kept, not just the part this build knows how
        # to read. The contract says receivers must preserve and pass
        # through keys they do not recognise, and a machine reporting
        # something a newer runtime added would otherwise have it silently
        # destroyed by an older server.
        self.store.put_payload(msg.asset_id, payload)

        registry = payload.get("registry")
        if not isinstance(registry, dict):
            return

        # The manifest is the machine's own declaration of what it is, and
        # it is the only naming authority. Merging it here is what lets an
        # application show a machine's name without composing one from its
        # class, which would be a second authority and a reach below the HAL.
        manifest = registry.get("manifest")
        if isinstance(manifest, dict) and manifest:
            merged = MessageToDict(asset.capabilities) if asset.HasField("capabilities") else {}
            merged.update(manifest)
            asset.capabilities.update(merged)

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
            # A new contact is the moment the mode means something. This
            # runs on the ingest path, so it must never block: issuing an
            # order is the same await the rest of this method already does,
            # and a machine that cannot take it is dropped, not retried.
            await self.investigate(track)

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

        await self.bus.publish(live.TRACK_UPDATED, self.track_view(track))

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
                "task": self.task_view(task),
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
        await self.bus.publish(live.TASK_UPDATED, {"task": self.task_view(task), "progress": 0.0})
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
        await self.bus.publish(live.TASK_UPDATED, {"task": self.task_view(task), "progress": 0.0})
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
            await self.bus.publish(live.ASSET_UPDATED, self.asset_view(asset))
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
            await self.bus.publish(live.TRACK_UPDATED, self.track_view(track))

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
        await self.bus.publish(live.TASK_UPDATED, {"task": self.task_view(task), "progress": 0.0})

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
