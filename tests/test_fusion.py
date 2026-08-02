"""Fusion: observations becoming tracks."""

from __future__ import annotations

import time

from link.v1.ontology_pb2 import Observation, Position, TrackState

from track.fusion import CONFIDENCE_CEILING, TrackManager
from track.ids import new_id, now_ts

SITE_LAT = 51.50450
SITE_LON = -0.12000


def observation(
    lat: float = SITE_LAT,
    lon: float = SITE_LON,
    entity_class: str = "person",
    confidence: float = 0.6,
    asset_id: str = "asset-1",
    entity_id: str | None = None,
) -> Observation:
    return Observation(
        observation_id=new_id(),
        entity_id=entity_id or new_id(),
        asset_id=asset_id,
        position=Position(latitude_deg=lat, longitude_deg=lon),
        confidence=confidence,
        entity_class=entity_class,
        timestamp=now_ts(),
    )


def test_two_nearby_observations_become_one_track(store, settings):
    manager = TrackManager(store, settings)

    first = manager.ingest(observation())
    # About 10 meters north, well inside the association gate.
    second = manager.ingest(observation(lat=SITE_LAT + 0.00009))

    assert first.created_track is True
    assert second.created_track is False
    assert second.track.track_id == first.track.track_id
    assert len(store.list_tracks()) == 1


def test_distant_observations_become_separate_tracks(store, settings):
    manager = TrackManager(store, settings)

    manager.ingest(observation())
    # About 500 meters away, far outside the gate.
    far = manager.ingest(observation(lat=SITE_LAT + 0.0045))

    assert far.created_track is True
    assert len(store.list_tracks()) == 2


def test_different_classes_do_not_merge(store, settings):
    manager = TrackManager(store, settings)

    manager.ingest(observation(entity_class="person"))
    other = manager.ingest(observation(lat=SITE_LAT + 0.00009, entity_class="vehicle"))

    assert other.created_track is True


def test_unknown_class_associates_with_anything(store, settings):
    """A sensor that cannot classify still contributes to the right track."""
    manager = TrackManager(store, settings)

    known = manager.ingest(observation(entity_class="person"))
    vague = manager.ingest(observation(lat=SITE_LAT + 0.00009, entity_class="unknown"))

    assert vague.track.track_id == known.track.track_id
    # The vague report must not erase what we already knew.
    assert store.get_entity(known.track.entity_id).entity_class == "person"


def test_class_from_a_newer_vocabulary_is_kept(store, settings):
    """A class this build has never heard of is stored, not discarded."""
    manager = TrackManager(store, settings)

    result = manager.ingest(observation(entity_class="ground_drone_swarm"))

    assert result.entity.entity_class == "ground_drone_swarm"


def test_same_entity_identity_always_matches_its_track(store, settings):
    """An asset reporting one identity twice is believed, whatever the geometry."""
    manager = TrackManager(store, settings)
    entity_id = new_id()

    first = manager.ingest(observation(entity_id=entity_id))
    # Far enough that geometry alone would start a new track.
    second = manager.ingest(observation(lat=SITE_LAT + 0.004, entity_id=entity_id))

    assert second.track.track_id == first.track.track_id


def test_provisional_identity_is_resolved_and_recorded(store, settings):
    """When geometry says two identities are one thing, the graph records it."""
    manager = TrackManager(store, settings)

    first = manager.ingest(observation(entity_id=new_id(), asset_id="asset-1"))
    provisional = new_id()
    second = manager.ingest(
        observation(lat=SITE_LAT + 0.00009, entity_id=provisional, asset_id="asset-2")
    )

    assert second.track.track_id == first.track.track_id
    assert store.resolve_entity(provisional) == first.track.entity_id
    predicates = [r.predicate for r in store.list_relationships()]
    assert "same_as" in predicates


def test_confidence_rises_with_corroboration_but_never_reaches_certainty(store, settings):
    manager = TrackManager(store, settings)

    result = manager.ingest(observation(confidence=0.99))
    for _ in range(30):
        result = manager.ingest(observation(lat=SITE_LAT + 0.00001, confidence=0.99))

    assert result.track.confidence > 0.9
    assert result.track.confidence <= CONFIDENCE_CEILING


def test_velocity_is_derived_from_movement(store, settings):
    manager = TrackManager(store, settings)
    entity_id = new_id()

    manager.ingest(observation(entity_id=entity_id))
    time.sleep(0.05)
    moved = manager.ingest(observation(lat=SITE_LAT + 0.00018, entity_id=entity_id))

    assert moved.track.velocity.speed_mps > 0
    # Heading roughly north.
    assert moved.track.velocity.course_deg < 10 or moved.track.velocity.course_deg > 350


def test_unobserved_track_goes_lost_then_closes(store, settings):
    """Ageing is measured from the last observation, not the last database write."""
    manager = TrackManager(store, settings)
    result = manager.ingest(observation())

    # Nothing has been seen for longer than the lost threshold.
    track = result.track
    track.history[-1].timestamp.seconds -= int(settings.track_lost_after_s + 1)
    store.put_track(track)

    changed = manager.sweep()
    assert [t.state for t in changed] == [TrackState.TRACK_STATE_LOST]

    # A lost track keeps its position, so an operator still sees where it was.
    assert store.get_track(track.track_id).position.latitude_deg == SITE_LAT

    track = store.get_track(track.track_id)
    track.history[-1].timestamp.seconds -= int(settings.track_close_after_s)
    store.put_track(track)

    changed = manager.sweep()
    assert [t.state for t in changed] == [TrackState.TRACK_STATE_CLOSED]
