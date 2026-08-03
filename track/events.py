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

    @property
    def severities(self) -> dict:
        """Every event kind that has been given a colour."""
        return dict(self._d["severity"])

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

    def place_phrase(self, zone_name: str) -> str:
        """Where something is, as a phrase that can stand on its own.

        Empty when we do not know, so the caller can say nothing rather than
        say somewhere vague.
        """
        if not zone_name:
            return ""
        return self._d["fragments"]["place_inside"].format(zone=zone_name)

    # -- autonomy ----------------------------------------------------------

    @property
    def autonomy_modes(self) -> dict[str, str]:
        """Every mode this platform can actually enforce, and its word."""
        return dict(self._d["autonomy_modes"])

    @property
    def default_autonomy_mode(self) -> str:
        return self._d["default_autonomy_mode"]

    def knows_autonomy_mode(self, mode: str) -> bool:
        return mode in self._d["autonomy_modes"]

    def autonomy_choices(self) -> str:
        """The modes, listed for a refusal an operator has to act on."""
        return ", ".join(self._d["autonomy_modes"].values())

    def is_self_issued(self, channel: str) -> bool:
        """Did a station give this order on its own, with nobody asked?"""
        return channel in self._d["self_issued_channels"]

    def time_of_day(self, when, today=None) -> str:
        """A clock time as an operator reads it, from the language file.

        Anything that did not happen today carries its date. A bare clock
        time reads as today, which is wrong for an order still running
        across midnight or given before a long outage.
        """
        key = "time_of_day"
        if today is not None and when.date() != today:
            key = "time_of_day_dated"
        return when.strftime(self._d[key])

    def task_reason(self, channel: str, who: str, at: str) -> str:
        """Why a machine is doing what it is doing, in one phrase.

        Composed here rather than in an application. An application deciding
        this for itself has to enumerate the channel vocabulary, and every
        channel it has not heard of falls through to whichever branch was
        written last. That is how an order ends up attributed to someone who
        never gave it.

        An order with nobody on record gets no reason at all. Saying "an
        order was given at 14:32" reads as an unnamed person having given
        it, and calling it self-issued would invent a motive the record does
        not support. The feed calls the same order the system's; neither
        surface names a person, so neither can contradict the other.
        """
        reasons = self._d["task_reasons"]
        if self.is_self_issued(channel):
            return reasons["self_issued"]
        if not who:
            return ""
        if at:
            return reasons["by_person_at"].format(who=who, at=at)
        return reasons["by_person"].format(who=who)

    def track_name(self, entity_class: str, confidence: float) -> str:
        """What to call a contact on screen.

        Resolved here for the same reason asset names are: an application
        that built this out of an entity class would be a second naming
        authority, and the hedge would be the first thing to fall off.
        """
        name = self.template("track_name").format(
            qualifier_cap=self.qualifier(confidence),
            label=self.class_label(entity_class),
        ).strip()
        return name[:1].upper() + name[1:]

    def source_system(self) -> str:
        return self._d["sources"]["system"]

    def source_seen_by(self, asset_name: str) -> str:
        return self._d["sources"]["seen_by"].format(asset=asset_name)

    def source_changed_by(self, who: str) -> str:
        """Who changed a setting. Not an order, so not worded as one."""
        return self._d["sources"]["changed_by"].format(who=who)

    def source_ordered_by(self, who: str, channel: str) -> str:
        """Who ordered something and how, for the feed's source line.

        An order nobody was asked for names nobody, so this line agrees with
        the reason on the order itself. Both consult the same list.

        A channel this build has never heard of is shown as sent rather than
        dropped, the same as an unfamiliar entity class or order type: a
        newer station's vocabulary is information, and silently losing the
        "how" leaves the operator reading a bare name.
        """
        if self.is_self_issued(channel):
            return self._d["sources"]["self_issued"].format(
                channel=self.channel_phrase(channel)
            )
        channel_phrase = self.channel_phrase(channel)
        if channel_phrase:
            return self._d["sources"]["ordered_by_channel"].format(who=who, channel=channel_phrase)
        return self._d["sources"]["ordered_by"].format(who=who)

    def channel_phrase(self, channel: str) -> str:
        """How an order arrived, in words.

        A channel this build has never heard of still has to reach the
        operator, because losing the "how" leaves them reading a bare name.
        It reaches them as the fact that we do not know the route, not as
        the token itself: unlike an entity class, a channel is a free-form
        string a caller chose, and "task_api_v2" on an operator's screen is
        system vocabulary crossing the waterline. Naming it another system
        would be worse still, because a future station using its own channel
        would have an operator's own click reported back to them as somebody
        else's. The value is preserved in the record either way; this is
        only how it is read out.
        """
        known = self._d["channels"].get(channel, "")
        if known:
            return known
        return self._d["channels"]["unknown"] if channel else ""


class EventWriter:
    """Builds event-feed entries from world model changes."""

    def __init__(self, language: Language):
        self.lang = language
        self._person_lookup = None

    def bind_person_lookup(self, lookup) -> None:
        """How to turn a principal into a name an operator can read."""
        self._person_lookup = lookup

    def name_person(self, principal_id: str) -> str:
        """Who did it, in words.

        An identifier must never reach a sentence. If we cannot name the
        person, the sentence says so plainly rather than printing the
        identifier we happen to hold.
        """
        name = self._person_lookup(principal_id) if self._person_lookup else ""
        return name or self.lang.fragment("unknown_person")

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

    def autonomy_changed(self, asset: Asset, mode: str, principal_id: str) -> Event:
        """A machine's mode was switched, and by whom.

        The kind is the mode itself, so each mode carries its own sentence
        and its own colour from the data file: going automatic is worth an
        operator's attention, going manual is not.
        """
        kind = f"autonomy_{mode}"
        text = self.lang.template(kind).format(asset=self.lang.asset_name(asset))
        return new_event(
            text=_sentence(text),
            severity=self.lang.severity(kind),
            source=self.lang.source_changed_by(self.name_person(principal_id)),
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
        # Three cases, in the order the facts rank.
        #
        # A self-issued order says how it arrived and names nobody, even
        # though it carries a principal or lacks one: the channel is the
        # meaningful fact and no person was asked. A person-issued order
        # names them. Anything else is the system's, because an Issuer with
        # no principal and no self-issued channel tells us nothing about
        # who acted, and "someone signed in" would assert a person the
        # record does not have.
        issuer = task.issued_by if task.HasField("issued_by") else None
        if kind != "task_issued" or issuer is None:
            source = self.lang.source_system()
        elif self.lang.is_self_issued(issuer.channel):
            source = self.lang.source_ordered_by("", issuer.channel)
        elif issuer.principal_id:
            source = self.lang.source_ordered_by(
                self.name_person(issuer.principal_id), issuer.channel
            )
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
