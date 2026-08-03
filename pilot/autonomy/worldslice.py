"""The machine's own copy of what it knows.

The disconnection law says every asset is fully functional alone. That is
only true if the machine keeps its own world model rather than asking the
server what it is looking at. This is that slice: what this machine has
seen, what it has been told to do, and where it has been.

It is small on purpose. A machine does not need the fleet's picture to do
its own job, and a slice that tried to mirror the whole world model would
turn a connectivity feature into a dependency, which is the thing the law
forbids.

Entity identity is local. A machine that sees the same thing twice gives
both sightings one locally-generated identity, and the world model resolves
that against what other machines saw. The machine never waits for that
resolution to keep working.

A caution the contract makes necessary: the identity a machine assigns is
provisional, but nothing on the wire marks it as provisional. `entity_id`
in an Observation is a ULID whether it came from a machine's guess or from
the world model's resolution, and the two are indistinguishable to a
receiver. The world model treats identities from assets as provisional by
convention rather than because the contract says so. Worth remembering
before anything starts trusting an asset-assigned identity as durable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from link.v1.ontology_pb2 import Task
from ulid import ULID

from pilot import geo
from pilot.hal.interfaces import Detection

log = logging.getLogger(__name__)

# How close two sightings of the same class must be, in meters, to be
# treated as the same thing by this machine. Deliberately generous: the
# machine's job is to avoid inventing a new identity every frame, not to
# do the fusion the world model does properly with everyone's data.
SAME_THING_M = 12.0

# How long a local identity survives without being seen again.
FORGET_AFTER_S = 30.0


@dataclass
class LocalEntity:
    """Something this machine believes it has been looking at."""

    entity_id: str
    entity_class: str
    latitude_deg: float
    longitude_deg: float
    last_seen: float
    times_seen: int = 1


@dataclass
class WorldSlice:
    """What this machine knows without asking anyone."""

    entities: dict[str, LocalEntity] = field(default_factory=dict)
    current_task: Task | None = None
    # Where the machine started, which is where "return home" means.
    home: tuple[float, float] | None = None

    def resolve(
        self, detection: Detection, latitude_deg: float, longitude_deg: float
    ) -> LocalEntity:
        """Give a sighting an identity, reusing one where it plainly fits."""
        now = time.monotonic()
        self._forget(now)

        for entity in self.entities.values():
            if entity.entity_class != detection.entity_class:
                continue
            distance = geo.distance_m(
                entity.latitude_deg, entity.longitude_deg, latitude_deg, longitude_deg
            )
            if distance <= SAME_THING_M:
                entity.latitude_deg = latitude_deg
                entity.longitude_deg = longitude_deg
                entity.last_seen = now
                entity.times_seen += 1
                return entity

        entity = LocalEntity(
            entity_id=str(ULID()),
            entity_class=detection.entity_class,
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            last_seen=now,
        )
        self.entities[entity.entity_id] = entity
        return entity

    def _forget(self, now: float) -> None:
        stale = [
            entity_id
            for entity_id, entity in self.entities.items()
            if now - entity.last_seen > FORGET_AFTER_S
        ]
        for entity_id in stale:
            del self.entities[entity_id]
