"""Zone rules, and the words an operator actually reads."""

from __future__ import annotations

import re

from link.v1.ontology_pb2 import (
    Asset,
    Entity,
    Observation,
    Position,
    ThreatLevel,
    Track,
    ZoneRule,
)

from track.events import EventWriter, Language
from track.fusion import TrackManager
from track.ids import new_id, now_ts
from track.zones import ZoneEvaluator

from tests.conftest import SITE_LAT, SITE_LON

# Words that belong to the system, never to the operator. The waterline law
# says an operator sees a map, things on the map, and plain sentences.
JARGON = re.compile(
    r"entity_id|track_id|asset_id|observation|ontology|schema|enum|null|"
    r"TASK_STATE|ASSET_STATUS|proto|payload",
    re.IGNORECASE,
)


def _observation(lat: float, lon: float, entity_class: str = "person", confidence: float = 0.42):
    return Observation(
        observation_id=new_id(),
        entity_id=new_id(),
        asset_id="asset-1",
        position=Position(latitude_deg=lat, longitude_deg=lon),
        confidence=confidence,
        entity_class=entity_class,
        timestamp=now_ts(),
    )


# -- zones -----------------------------------------------------------------


def test_entering_a_protected_zone_alerts_and_raises_threat(store, settings, gate_zone):
    manager = TrackManager(store, settings)
    evaluator = ZoneEvaluator(store)

    inside = manager.ingest(_observation(SITE_LAT + 0.0003, SITE_LON))
    transition = evaluator.evaluate(inside.track)

    assert [z.name for z in transition.entered] == ["Gate 3"]
    assert [z.name for z in transition.alert_on_entered] == ["Gate 3"]
    assert transition.threat_level == ThreatLevel.THREAT_LEVEL_MEDIUM


def test_leaving_a_zone_is_detected_once(store, settings, gate_zone):
    manager = TrackManager(store, settings)
    evaluator = ZoneEvaluator(store)
    entity_id = new_id()

    track = manager.ingest(_observation(SITE_LAT + 0.0003, SITE_LON)).track
    evaluator.evaluate(track)

    track.position.latitude_deg = SITE_LAT - 0.002
    left = evaluator.evaluate(track)
    assert [z.name for z in left.exited] == ["Gate 3"]

    # Evaluating again reports no further change.
    assert evaluator.evaluate(track).changed is False


def test_a_rule_this_build_does_not_understand_is_left_alone(store, settings, gate_zone):
    """An older server must not break on, or delete, a newer rule."""
    gate_zone.rules.append(ZoneRule(rule_type="alert_on_loitering", parameters={"minutes": "5"}))
    store.put_zone(gate_zone)

    manager = TrackManager(store, settings)
    evaluator = ZoneEvaluator(store)

    track = manager.ingest(_observation(SITE_LAT + 0.0003, SITE_LON)).track
    transition = evaluator.evaluate(track)

    assert [z.name for z in transition.alert_on_entered] == ["Gate 3"]
    stored = store.get_zone(gate_zone.zone_id)
    assert "alert_on_loitering" in [r.rule_type for r in stored.rules]


def test_an_unrecognised_threat_level_is_ignored_not_fatal(store, settings, gate_zone):
    gate_zone.rules[0].parameters["threat_level"] = "catastrophic"
    store.put_zone(gate_zone)

    manager = TrackManager(store, settings)
    track = manager.ingest(_observation(SITE_LAT + 0.0003, SITE_LON)).track
    transition = ZoneEvaluator(store).evaluate(track)

    assert transition.alert_on_entered  # the alert still fires
    assert transition.threat_level is None  # the unreadable value is skipped


def test_place_name_prefers_the_smaller_zone(store, settings, gate_zone):
    assert ZoneEvaluator(store).place_name(
        Position(latitude_deg=SITE_LAT + 0.0003, longitude_deg=SITE_LON)
    ) == "Gate 3"
    assert ZoneEvaluator(store).place_name(
        Position(latitude_deg=SITE_LAT - 0.01, longitude_deg=SITE_LON)
    ) == ""


# -- language --------------------------------------------------------------


def language() -> Language:
    from track.config import Settings

    return Language.from_file(Settings().event_templates_path)


def writer() -> EventWriter:
    return EventWriter(language())


def test_a_doubtful_detection_says_so(store, settings):
    """The honesty law: never sound more certain than we are."""
    manager = TrackManager(store, settings)
    result = manager.ingest(_observation(SITE_LAT, SITE_LON, confidence=0.42))

    event = writer().track_created(result.track, result.entity, _observation(SITE_LAT, SITE_LON))

    assert "possible" in event.text.lower()
    assert "low confidence" in event.text.lower()


def test_a_strong_detection_drops_the_hedge(store, settings):
    manager = TrackManager(store, settings)
    result = manager.ingest(_observation(SITE_LAT, SITE_LON, confidence=0.95))

    event = writer().track_created(result.track, result.entity, _observation(SITE_LAT, SITE_LON))

    assert "possible" not in event.text.lower()
    assert "high confidence" in event.text.lower()


def test_a_class_from_a_newer_sensor_reaches_the_operator(store, settings):
    """Unknown vocabulary is shown in plain words, never dropped or hidden."""
    manager = TrackManager(store, settings)
    result = manager.ingest(_observation(SITE_LAT, SITE_LON, entity_class="ground_swarm"))

    event = writer().track_created(result.track, result.entity, _observation(SITE_LAT, SITE_LON))

    assert "ground swarm" in event.text.lower()


def test_a_machine_without_a_name_still_reads_as_words(store):
    """An operator must never be shown an identifier."""
    asset = Asset(asset_id="01HQZX9K7T4M2N8P6R3W5Y1B0C", asset_class="ugv")
    name = language().asset_name(asset)

    assert "Ground vehicle" in name
    assert asset.asset_id not in name


def test_a_named_machine_uses_its_name(store):
    asset = Asset(asset_id=new_id(), asset_class="ugv")
    asset.capabilities.update({"name": "UGV-1"})
    assert language().asset_name(asset) == "UGV-1"


def test_generated_sentences_carry_no_system_words(store, settings, gate_zone):
    manager = TrackManager(store, settings)
    result = manager.ingest(_observation(SITE_LAT + 0.0003, SITE_LON))
    ew = writer()

    asset = Asset(asset_id=new_id(), asset_class="ugv")
    asset.capabilities.update({"name": "UGV-1"})
    asset.battery_fraction = 0.91

    sentences = [
        ew.track_created(result.track, result.entity, _observation(SITE_LAT, SITE_LON), "Gate 3").text,
        ew.track_lost(result.track, result.entity, "Gate 3").text,
        ew.zone_entry(result.track, result.entity, gate_zone).text,
        ew.zone_exit(result.track, result.entity, gate_zone).text,
        ew.asset_online(asset).text,
        ew.asset_offline(asset).text,
        ew.asset_fault(asset).text,
    ]

    for sentence in sentences:
        assert not JARGON.search(sentence), f"system wording reached the operator: {sentence}"
        assert sentence[0].isupper()
        assert sentence.endswith((".", "?"))


def test_battery_is_only_mentioned_when_there_is_one(store):
    """A mains-powered sensor must not be described as having an empty battery."""
    ew = writer()
    mains = Asset(asset_id=new_id(), asset_class="fixed_sensor")
    mains.capabilities.update({"name": "Gate camera"})

    assert "battery" not in ew.asset_online(mains).text.lower()

    battery_powered = Asset(asset_id=new_id(), asset_class="ugv")
    battery_powered.battery_fraction = 0.0
    assert "battery 0 percent" in ew.asset_online(battery_powered).text.lower()
