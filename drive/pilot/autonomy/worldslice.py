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

Since ADR-0005 the slice writes through to a LocalStore, so what the
machine knows survives the process. The slice given no store behaves as
it always did, in memory, which is what unit tests and tools want.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from link.v1.ontology_pb2 import Task
from ulid import ULID

from pilot import geo
from pilot.autonomy.local_world import LocalStore
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


class WorldSlice:
    """What this machine knows without asking anyone."""

    def __init__(self, store: LocalStore | None = None):
        self._store = store
        self.entities: dict[str, LocalEntity] = {}
        self._current_task: Task | None = None
        self._home: tuple[float, float] | None = None
        if store is not None:
            self._recover(store)

    def _recover(self, store: LocalStore) -> None:
        """What the last process knew is what this one starts with."""
        for row in store.entities():
            entity = LocalEntity(
                entity_id=row["entity_id"],
                entity_class=row["entity_class"],
                latitude_deg=row["latitude_deg"],
                longitude_deg=row["longitude_deg"],
                last_seen=row["last_seen"],
                times_seen=row["times_seen"],
            )
            self.entities[entity.entity_id] = entity
        self._current_task = store.current_task()
        self._home = store.home()

    # The current order and home are plain attributes to their readers and
    # writers; the store is written through underneath so a power cut
    # between assignments loses nothing.

    @property
    def current_task(self) -> Task | None:
        return self._current_task

    @current_task.setter
    def current_task(self, task: Task | None) -> None:
        self._current_task = task
        if self._store is not None:
            self._store.set_current_task(task)

    @property
    def home(self) -> tuple[float, float] | None:
        return self._home

    @home.setter
    def home(self, value: tuple[float, float] | None) -> None:
        self._home = value
        if self._store is None:
            return
        # Memory and the store change together or the store stops being
        # the truth; clearing is written through for the same reason
        # setting is, even though nothing clears home today.
        if value is None:
            self._store.clear_home()
            self._store.append("home_cleared")
        else:
            self._store.set_home(value[0], value[1])
            self._store.append(
                "home_set", latitude_deg=value[0], longitude_deg=value[1]
            )

    def journal(self, kind: str, **detail) -> None:
        """Record a decision or transition, if this machine keeps a journal."""
        if self._store is not None:
            self._store.append(kind, **detail)

    def resolve(
        self, detection: Detection, latitude_deg: float, longitude_deg: float
    ) -> LocalEntity:
        """Give a sighting an identity, reusing one where it plainly fits."""
        # Wall clock, not monotonic: last_seen has to mean the same thing
        # to the process that wrote it and the process that reboots into it.
        now = time.time()
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
                self._save(entity)
                return entity

        entity = LocalEntity(
            entity_id=str(ULID()),
            entity_class=detection.entity_class,
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            last_seen=now,
        )
        self.entities[entity.entity_id] = entity
        self._save(entity)
        return entity

    def _save(self, entity: LocalEntity) -> None:
        if self._store is not None:
            self._store.save_entity(
                entity_id=entity.entity_id,
                entity_class=entity.entity_class,
                latitude_deg=entity.latitude_deg,
                longitude_deg=entity.longitude_deg,
                last_seen=entity.last_seen,
                times_seen=entity.times_seen,
            )

    def _forget(self, now: float) -> None:
        stale = [
            entity_id
            for entity_id, entity in self.entities.items()
            if now - entity.last_seen > FORGET_AFTER_S
        ]
        for entity_id in stale:
            del self.entities[entity_id]
            if self._store is not None:
                self._store.forget_entity(entity_id)
