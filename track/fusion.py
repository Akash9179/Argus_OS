"""Observation to track fusion.

The association step (deciding whether a new observation belongs to a track
we already have) is deliberately isolated behind the Associator protocol.
Version 1 ships nearest-neighbor with time and distance gates; replacing it
with a probabilistic tracker later means writing one class, not touching
this module's callers.

Nothing here inspects what kind of machine produced an observation. Fusion
reads positions, times, classes, and confidences only, so it works
unchanged for ground, air, surface, and fixed sensors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from link.v1.ontology_pb2 import (
    Entity,
    Observation,
    Position,
    Relationship,
    Track,
    TrackPoint,
    TrackState,
    Velocity,
)

from track import geo
from track.config import Settings
from track.ids import epoch_now, new_id, now_ts, to_epoch
from track.store import Store

# Track confidence is a weighted blend of its previous value and each new
# observation. Corroboration raises confidence honestly, but it is capped
# below 1.0: the system never claims certainty.
CONFIDENCE_WEIGHT_NEW = 0.4
CONFIDENCE_CEILING = 0.99
HISTORY_LIMIT = 200

# An entity class that means "I do not know what this is". Observations
# carrying it associate with a track of any class, and never overwrite a
# more specific classification.
UNKNOWN_CLASS = "unknown"


def classes_compatible(a: str, b: str) -> bool:
    """Whether two class strings could describe the same thing.

    Compares strings only. It never enumerates the vocabulary, so a class
    this build has never seen still associates with itself and is never
    rejected for being unfamiliar.
    """
    if not a or not b or a == UNKNOWN_CLASS or b == UNKNOWN_CLASS:
        return True
    return a == b


class Associator(Protocol):
    """Decides which existing track an observation belongs to, if any."""

    def associate(self, obs: Observation, candidates: Sequence[Track]) -> str | None:
        """Return the track_id to merge into, or None to start a new track."""


class NearestNeighborAssociator:
    """Closest compatible track within a distance gate wins.

    Candidates are rejected if they are too far away, too old, or of an
    incompatible class. Among the survivors the nearest wins.
    """

    def __init__(self, max_distance_m: float, max_age_s: float, store: Store):
        self._max_distance_m = max_distance_m
        self._max_age_s = max_age_s
        self._store = store

    def associate(self, obs: Observation, candidates: Sequence[Track]) -> str | None:
        obs_time = to_epoch(obs.timestamp) or epoch_now()
        best_id: str | None = None
        best_distance = self._max_distance_m

        for track in candidates:
            if track.state == TrackState.TRACK_STATE_CLOSED:
                continue
            if not classes_compatible(obs.entity_class, _track_class(self._store, track)):
                continue
            age = abs(obs_time - (last_observed_at(track) or obs_time))
            if age > self._max_age_s:
                continue
            distance = geo.distance_m(obs.position, track.position)
            if distance <= best_distance:
                best_distance = distance
                best_id = track.track_id

        return best_id


def _track_class(store: Store, track: Track) -> str:
    entity = store.get_entity(track.entity_id)
    return entity.entity_class if entity else ""


def last_observed_at(track: Track) -> float:
    """When this track was last actually observed, in epoch seconds.

    Read from the track's own history rather than from when its database
    row was last written, because a row is also written when the track
    merely changes state. Using the row's write time would restart the
    ageing clock every time a track was marked lost, so a lost track would
    never close.
    """
    if not track.history:
        return 0.0
    return to_epoch(track.history[-1].timestamp)


@dataclass
class FusionResult:
    """What ingesting one observation did to the world model."""

    track: Track
    entity: Entity
    created_track: bool


class TrackManager:
    """Owns track creation, update, and lifecycle."""

    def __init__(self, store: Store, settings: Settings, associator: Associator | None = None):
        self._store = store
        self._settings = settings
        self._associator = associator or NearestNeighborAssociator(
            max_distance_m=settings.assoc_max_distance_m,
            max_age_s=settings.assoc_max_age_s,
            store=store,
        )

    def ingest(self, obs: Observation) -> FusionResult:
        """Fuse one observation into the world model."""
        self._store.put_observation(obs)

        track = self._find_track_for(obs)
        if track is None:
            return self._create(obs)
        return self._update(track, obs)

    # -- association -------------------------------------------------------

    def _find_track_for(self, obs: Observation) -> Track | None:
        """Find the track this observation belongs to.

        Identity first: an asset that reports the same entity identity twice
        is telling us it believes it is the same thing, and that belief is
        stronger evidence than geometry. Geometry is the fallback.
        """
        canonical = self._store.resolve_entity(obs.entity_id)
        live = self._store.list_tracks(
            states=[TrackState.TRACK_STATE_ACTIVE, TrackState.TRACK_STATE_LOST]
        )

        for track in live:
            if track.entity_id == canonical:
                return track

        track_id = self._associator.associate(obs, live)
        if track_id is None:
            return None

        track = self._store.get_track(track_id)
        if track is not None and obs.entity_id != track.entity_id:
            # Geometry says the asset's provisional identity is something we
            # already know. Record the resolution and the graph edge.
            self._store.alias_entity(obs.entity_id, track.entity_id)
            self._store.put_relationship(
                Relationship(
                    relationship_id=new_id(),
                    subject_id=obs.entity_id,
                    predicate="same_as",
                    object_id=track.entity_id,
                    confidence=obs.confidence,
                    timestamp=now_ts(),
                )
            )
        return track

    # -- create and update -------------------------------------------------

    def _create(self, obs: Observation) -> FusionResult:
        entity = Entity(
            entity_id=obs.entity_id or new_id(),
            entity_class=obs.entity_class,
            first_seen=obs.timestamp,
            last_seen=obs.timestamp,
        )
        for key, value in obs.attributes.items():
            entity.attributes[key] = value
        self._store.put_entity(entity)

        track = Track(
            track_id=new_id(),
            entity_id=entity.entity_id,
            state=TrackState.TRACK_STATE_ACTIVE,
            position=obs.position,
            confidence=min(obs.confidence, CONFIDENCE_CEILING),
        )
        track.contributing_asset_ids.append(obs.asset_id)
        track.observation_ids.append(obs.observation_id)
        track.history.append(
            TrackPoint(timestamp=obs.timestamp, position=obs.position, velocity=Velocity())
        )
        self._store.put_track(track)
        return FusionResult(track=track, entity=entity, created_track=True)

    def _update(self, track: Track, obs: Observation) -> FusionResult:
        previous_point = track.history[-1] if track.history else None
        # A copy, not a reference: track.position is overwritten immediately
        # below, and the velocity calculation needs where the track was.
        previous_position = Position()
        previous_position.CopyFrom(track.position)

        track.position.CopyFrom(obs.position)
        track.state = TrackState.TRACK_STATE_ACTIVE
        track.confidence = min(
            CONFIDENCE_CEILING,
            (1 - CONFIDENCE_WEIGHT_NEW) * track.confidence + CONFIDENCE_WEIGHT_NEW * obs.confidence,
        )

        velocity = self._velocity(previous_point, previous_position, obs)
        if velocity is not None:
            track.velocity.CopyFrom(velocity)

        if obs.asset_id and obs.asset_id not in track.contributing_asset_ids:
            track.contributing_asset_ids.append(obs.asset_id)
        track.observation_ids.append(obs.observation_id)
        track.history.append(
            TrackPoint(timestamp=obs.timestamp, position=obs.position, velocity=track.velocity)
        )
        while len(track.history) > HISTORY_LIMIT:
            del track.history[0]

        self._store.put_track(track)

        entity = self._store.get_entity(track.entity_id) or Entity(
            entity_id=track.entity_id, first_seen=obs.timestamp
        )
        # A specific classification is never overwritten by "unknown", and
        # an unfamiliar class string is stored as sent.
        if obs.entity_class and obs.entity_class != UNKNOWN_CLASS:
            entity.entity_class = obs.entity_class
        elif not entity.entity_class:
            entity.entity_class = obs.entity_class
        for key, value in obs.attributes.items():
            entity.attributes[key] = value
        entity.last_seen.CopyFrom(obs.timestamp)
        self._store.put_entity(entity)

        return FusionResult(track=track, entity=entity, created_track=False)

    @staticmethod
    def _velocity(previous_point: TrackPoint | None, previous_position, obs: Observation) -> Velocity | None:
        if previous_point is None:
            return None
        dt = to_epoch(obs.timestamp) - to_epoch(previous_point.timestamp)
        if dt <= 0:
            return None
        distance = geo.distance_m(previous_position, obs.position)
        return Velocity(
            speed_mps=distance / dt,
            course_deg=geo.bearing_deg(previous_position, obs.position) if distance > 0.1 else 0.0,
        )

    # -- lifecycle ---------------------------------------------------------

    def sweep(self) -> list[Track]:
        """Age out tracks that have stopped being observed.

        Returns the tracks whose state changed, so the caller can announce
        them. A lost track keeps its last position: an operator would rather
        see where something was last seen than see it vanish.
        """
        changed: list[Track] = []
        now = epoch_now()

        for track in self._store.list_tracks(
            states=[TrackState.TRACK_STATE_ACTIVE, TrackState.TRACK_STATE_LOST]
        ):
            age = now - (last_observed_at(track) or now)
            new_state = track.state
            if age > self._settings.track_close_after_s:
                new_state = TrackState.TRACK_STATE_CLOSED
            elif age > self._settings.track_lost_after_s:
                new_state = TrackState.TRACK_STATE_LOST

            if new_state != track.state:
                track.state = new_state
                self._store.put_track(track)
                changed.append(track)

        return changed
