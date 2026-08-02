"""Zone rule evaluation.

Zones are named places with meaning. This module answers two questions on
every track update: which zones is this thing inside now, and did that just
change. Rules attached to a zone decide whether a change is worth telling
the operator about, and may raise a track's threat level.

Rule types are an open vocabulary. A rule this build does not understand is
left alone and passed over, never treated as an error and never deleted: a
newer admin tool may have written it, and an older server must not destroy
what it cannot read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from link.v1.ontology_pb2 import Position, ThreatLevel, Track, Zone

from track import geo
from track.store import Store

RULE_ALERT_ON_ENTRY = "alert_on_entry"
RULE_ALERT_ON_EXIT = "alert_on_exit"

# Rule parameter that lets an admin say how serious entry into this zone is,
# for example threat_level: medium. Keeping the policy in zone data rather
# than in code means a site can tune what alarms it without a rebuild.
PARAM_THREAT_LEVEL = "threat_level"


@dataclass
class ZoneTransition:
    """What changed about a track's zone membership."""

    entered: list[Zone] = field(default_factory=list)
    exited: list[Zone] = field(default_factory=list)
    # Zones the track entered that carry an alert rule, so the caller knows
    # which transitions deserve an event.
    alert_on_entered: list[Zone] = field(default_factory=list)
    alert_on_exited: list[Zone] = field(default_factory=list)
    threat_level: int | None = None

    @property
    def changed(self) -> bool:
        return bool(self.entered or self.exited)


class ZoneEvaluator:
    """Evaluates zone membership and rules for tracks."""

    def __init__(self, store: Store):
        self._store = store

    def zones_at(self, position: Position) -> list[Zone]:
        """Every zone containing the given position."""
        return [z for z in self._store.list_zones() if geo.point_in_polygon(position, z.geometry)]

    def place_name(self, position: Position) -> str:
        """The best single place name for a position, for use in a sentence.

        The smallest containing zone wins, because "near Gate 3" tells an
        operator more than the name of the site it sits in.
        """
        containing = self.zones_at(position)
        if not containing:
            return ""
        return min(containing, key=lambda z: _area(z)).name

    def evaluate(self, track: Track) -> ZoneTransition:
        """Update a track's zone membership and report what changed."""
        now_zones = {z.zone_id: z for z in self.zones_at(track.position)}
        was_ids = self._store.zones_containing(track.track_id)

        transition = ZoneTransition()
        for zone_id, zone in now_zones.items():
            if zone_id not in was_ids:
                transition.entered.append(zone)
                if _has_rule(zone, RULE_ALERT_ON_ENTRY):
                    transition.alert_on_entered.append(zone)
                    level = _threat_from_rules(zone, RULE_ALERT_ON_ENTRY)
                    if level is not None:
                        transition.threat_level = max(transition.threat_level or 0, level)

        for zone_id in was_ids - set(now_zones):
            zone = self._store.get_zone(zone_id)
            if zone is None:
                continue
            transition.exited.append(zone)
            if _has_rule(zone, RULE_ALERT_ON_EXIT):
                transition.alert_on_exited.append(zone)

        if transition.changed:
            self._store.set_zone_membership(track.track_id, set(now_zones))

        return transition


def _has_rule(zone: Zone, rule_type: str) -> bool:
    return any(rule.rule_type == rule_type for rule in zone.rules)


def _threat_from_rules(zone: Zone, rule_type: str) -> int | None:
    """Read a threat level out of a rule's parameters, if it names one.

    An unrecognised level is ignored rather than rejected, so a value from
    a newer vocabulary never stops the rest of the rule from working.
    """
    for rule in zone.rules:
        if rule.rule_type != rule_type:
            continue
        raw = rule.parameters.get(PARAM_THREAT_LEVEL, "")
        if not raw:
            continue
        name = f"THREAT_LEVEL_{raw.strip().upper()}"
        try:
            return ThreatLevel.Value(name)
        except ValueError:
            continue
    return None


def _area(zone: Zone) -> float:
    """Rough planar area of a zone, used only to pick the smallest one."""
    verts = list(zone.geometry.exterior)
    if len(verts) < 3:
        return float("inf")
    total = 0.0
    for i, v in enumerate(verts):
        w = verts[(i + 1) % len(verts)]
        total += v.longitude_deg * w.latitude_deg - w.longitude_deg * v.latitude_deg
    return abs(total) / 2.0
