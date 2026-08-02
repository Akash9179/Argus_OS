"""Turning world model changes into sentences an operator can read.

Every sentence comes from the templates data file. This module contains the
assembly logic and no English, so changing what the operator reads never
means changing code, and system vocabulary cannot leak into the operator's
view by accident.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from link.v1.ontology_pb2 import Asset, Entity, Observation, Task, Track, Zone

from track.store import Event, new_event


class Language:
    """Operator-facing phrasing, loaded from the templates data file."""

    def __init__(self, data: dict):
        self._d = data

    @classmethod
    def from_file(cls, path: str | Path) -> "Language":
        return cls(yaml.safe_load(Path(path).read_text()))

    # -- words for things --------------------------------------------------

    def class_label(self, entity_class: str) -> str:
        """What to call an observed thing.

        An unfamiliar class is shown as sent rather than discarded, because
        a newer sensor's vocabulary is information, not an error.
        """
        if not entity_class:
            return self._d["unknown_class_label"]
        labels = self._d["class_labels"]
        if entity_class in labels:
            return labels[entity_class]
        return entity_class.replace("_", " ")

    def asset_name(self, asset: Asset | None, asset_id: str = "") -> str:
        """What to call one of our machines.

        A machine's name comes from its capability manifest, which is where
        per-machine facts belong. Without one, it gets a readable fallback
        instead of an identifier, because operators never read identifiers.
        """
        if asset is None:
            return self._fallback_name("", asset_id)

        name = ""
        if asset.HasField("capabilities"):
            value = asset.capabilities.fields.get("name")
            if value is not None and value.HasField("string_value"):
                name = value.string_value
        return name or self._fallback_name(asset.asset_class, asset.asset_id)

    def _fallback_name(self, asset_class: str, asset_id: str) -> str:
        labels = self._d["asset_class_labels"]
        class_label = labels.get(asset_class, self._d["unknown_asset_class_label"])
        return self._d["asset_fallback_name"].format(
            class_label=class_label, short_id=asset_id[-4:].upper() if asset_id else "?"
        )

    def task_phrase(self, task_type: str) -> str:
        phrases = self._d["task_phrases"]
        if task_type in phrases:
            return phrases[task_type]
        return self._d["unknown_task_phrase"].format(task_type=task_type.replace("_", " "))

    # -- confidence --------------------------------------------------------

    def confidence_phrase(self, confidence: float) -> str:
        for band in self._d["confidence"]["bands"]:
            if confidence < band["below"]:
                return band["phrase"]
        return self._d["confidence"]["bands"][-1]["phrase"]

    def qualifier(self, confidence: float) -> str:
        if confidence < self._d["confidence"]["qualifier_below"]:
            return self._d["confidence"]["qualifier"]
        return ""

    # -- assembly ----------------------------------------------------------

    def severity(self, kind: str) -> str:
        return self._d["severity"].get(kind, "info")

    def template(self, kind: str) -> str:
        return self._d["templates"][kind]

    def fragment(self, name: str, **kwargs) -> str:
        return self._d["fragments"][name].format(**kwargs)

    def error(self, name: str, **kwargs) -> str:
        """A refusal, in the operator's words rather than the system's."""
        return self._d["errors"][name].format(**kwargs)

    def place_clause(self, zone_name: str) -> str:
        if not zone_name:
            return self._d["fragments"]["place_none"]
        return self._d["fragments"]["place_near"].format(zone=zone_name)

    def source_system(self) -> str:
        return self._d["sources"]["system"]

    def source_seen_by(self, asset_name: str) -> str:
        return self._d["sources"]["seen_by"].format(asset=asset_name)

    def source_ordered_by(self, who: str, channel: str) -> str:
        channel_phrase = self._d["channels"].get(channel, "")
        if channel_phrase:
            return self._d["sources"]["ordered_by_channel"].format(who=who, channel=channel_phrase)
        return self._d["sources"]["ordered_by"].format(who=who)


class EventWriter:
    """Builds event-feed entries from world model changes."""

    def __init__(self, language: Language):
        self.lang = language

    # -- things in the world ----------------------------------------------

    def track_created(self, track: Track, entity: Entity, obs: Observation, zone_name: str = "") -> Event:
        text = self.lang.template("track_created").format(
            qualifier=self.lang.qualifier(track.confidence),
            label=self.lang.class_label(entity.entity_class),
            place=self.lang.place_clause(zone_name),
            confidence=self.lang.confidence_phrase(track.confidence),
        )
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity("track_created"),
            source=self.lang.source_seen_by(self._asset_name(obs.asset_id)),
            subject_kind="track",
            subject_id=track.track_id,
        )

    def track_lost(self, track: Track, entity: Entity, zone_name: str = "") -> Event:
        text = self.lang.template("track_lost").format(
            label=self.lang.class_label(entity.entity_class),
            place=self.lang.place_clause(zone_name),
        )
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity("track_lost"),
            source=self.lang.source_system(),
            subject_kind="track",
            subject_id=track.track_id,
        )

    def zone_entry(self, track: Track, entity: Entity, zone: Zone) -> Event:
        label = self.lang.class_label(entity.entity_class)
        qualifier = self.lang.qualifier(track.confidence)
        text = self.lang.template("zone_entry").format(
            qualifier_cap=qualifier.capitalize() if qualifier else self.lang.fragment("definite_article"),
            label=label,
            zone=zone.name,
        )
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity("zone_entry"),
            source=self.lang.source_system(),
            subject_kind="track",
            subject_id=track.track_id,
        )

    def zone_exit(self, track: Track, entity: Entity, zone: Zone) -> Event:
        text = self.lang.template("zone_exit").format(
            label=self.lang.class_label(entity.entity_class), zone=zone.name
        )
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity("zone_exit"),
            source=self.lang.source_system(),
            subject_kind="track",
            subject_id=track.track_id,
        )

    # -- our own machines --------------------------------------------------

    def asset_online(self, asset: Asset) -> Event:
        battery_clause = ""
        if asset.HasField("battery_fraction"):
            battery_clause = self.lang.fragment(
                "battery_clause", battery=round(asset.battery_fraction * 100)
            )
        text = self.lang.template("asset_online").format(
            asset=self.lang.asset_name(asset), battery_clause=battery_clause
        )
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity("asset_online"),
            source=self.lang.source_system(),
            subject_kind="asset",
            subject_id=asset.asset_id,
        )

    def asset_offline(self, asset: Asset) -> Event:
        text = self.lang.template("asset_offline").format(asset=self.lang.asset_name(asset))
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity("asset_offline"),
            source=self.lang.source_system(),
            subject_kind="asset",
            subject_id=asset.asset_id,
        )

    def asset_fault(self, asset: Asset) -> Event:
        text = self.lang.template("asset_fault").format(asset=self.lang.asset_name(asset))
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity("asset_fault"),
            source=self.lang.source_system(),
            subject_kind="asset",
            subject_id=asset.asset_id,
        )

    # -- orders ------------------------------------------------------------

    def task_event(self, kind: str, task: Task, asset: Asset | None, reason: str = "") -> Event:
        text = self.lang.template(kind).format(
            asset=self.lang.asset_name(asset, task.asset_id),
            task_phrase=self.lang.task_phrase(task.task_type),
            reason=reason or self.lang.fragment("no_reason"),
        )
        if kind == "task_issued" and task.HasField("issued_by"):
            source = self.lang.source_ordered_by(task.issued_by.principal_id, task.issued_by.channel)
        else:
            source = self.lang.source_system()
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity(kind),
            source=source,
            subject_kind="task",
            subject_id=task.task_id,
        )

    # -- helpers -----------------------------------------------------------

    def _asset_name(self, asset_id: str) -> str:
        asset = self._asset_lookup(asset_id) if self._asset_lookup else None
        return self.lang.asset_name(asset, asset_id)

    # Injected by the server so sentences can name machines. Kept as a
    # plain callable so this module needs no database of its own.
    _asset_lookup = None

    def bind_asset_lookup(self, lookup) -> None:
        self._asset_lookup = lookup


def _sentence(text: str) -> str:
    """Tidy a filled template: single spaces, capital first letter."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return cleaned
    return cleaned[0].upper() + cleaned[1:]
