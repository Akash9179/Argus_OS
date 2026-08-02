"""Durable storage for the world model.

Every ontology object is stored as its raw protobuf bytes, with a few
columns lifted out for querying. Storing the wire bytes rather than a
decoded structure is deliberate: protobuf preserves fields a newer sender
included that this build does not know about, so an older server never
silently destroys a newer asset's data. Decoding to JSON happens only at
the API edge.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from google.protobuf.message import Message
from link.v1.ontology_pb2 import (
    Asset,
    Entity,
    Mission,
    Observation,
    Relationship,
    Task,
    Track,
    Zone,
)

from track.ids import epoch_now, new_id, to_epoch

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY, asset_class TEXT, status INTEGER,
    last_heartbeat REAL, pb BLOB NOT NULL);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY, entity_class TEXT,
    first_seen REAL, last_seen REAL, pb BLOB NOT NULL);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY, entity_id TEXT, asset_id TEXT,
    ts REAL, pb BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS observations_entity ON observations(entity_id, ts);

CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY, entity_id TEXT, state INTEGER,
    updated REAL, pb BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS tracks_state ON tracks(state, updated);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY, asset_id TEXT, status INTEGER,
    updated REAL, pb BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS tasks_asset ON tasks(asset_id, updated);

CREATE TABLE IF NOT EXISTS zones (
    zone_id TEXT PRIMARY KEY, name TEXT, pb BLOB NOT NULL);

CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY, pb BLOB NOT NULL);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY, subject_id TEXT, predicate TEXT,
    object_id TEXT, ts REAL, pb BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS relationships_subject ON relationships(subject_id);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY, ts REAL, severity TEXT, text TEXT,
    source TEXT, subject_kind TEXT, subject_id TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS zone_membership (
    track_id TEXT NOT NULL, zone_id TEXT NOT NULL,
    PRIMARY KEY (track_id, zone_id));

-- Assets that cannot know an entity's durable identity assign a provisional
-- one. When fusion decides a provisional identity is an entity we already
-- know, the mapping is recorded here. The original observation is never
-- rewritten: observations are immutable, so resolution lives beside them.
CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL);
"""


@dataclass
class Event:
    """One line in the operator's event feed.

    Events are not part of the asset contract: they are the server's
    plain-language product, generated from templates in a data file. The
    text is written for an operator, never in system terminology.
    """

    event_id: str
    ts: float
    text: str
    # Maps to the fixed four-colour status language: "info" (neutral or
    # healthy, green), "attention" (amber), "act" (red), "offline" (grey).
    # Open vocabulary.
    severity: str
    # Operator-facing description of where this came from, for example
    # "UGV-1 camera" or "System".
    source: str
    # What the event is about, so a click can open it. Kind is one of
    # "track", "asset", "task", "zone", or empty.
    subject_kind: str = ""
    subject_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Store:
    """SQLite-backed durable store. Safe to call from multiple threads."""

    def __init__(self, path: str | Path):
        p = Path(path)
        if str(p) != ":memory:":
            p.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(p), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- generic helpers ---------------------------------------------------

    def _write(self, sql: str, params: Sequence) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _rows(self, sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    @staticmethod
    def _decode(rows: list[sqlite3.Row], kind: type[Message]) -> list:
        return [kind.FromString(r["pb"]) for r in rows]

    # -- assets ------------------------------------------------------------

    def put_asset(self, asset: Asset) -> None:
        self._write(
            "INSERT INTO assets (asset_id, asset_class, status, last_heartbeat, pb) "
            "VALUES (?,?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET "
            "asset_class=excluded.asset_class, status=excluded.status, "
            "last_heartbeat=excluded.last_heartbeat, pb=excluded.pb",
            (
                asset.asset_id,
                asset.asset_class,
                int(asset.status),
                to_epoch(asset.last_heartbeat),
                asset.SerializeToString(),
            ),
        )

    def get_asset(self, asset_id: str) -> Asset | None:
        rows = self._rows("SELECT pb FROM assets WHERE asset_id=?", (asset_id,))
        return Asset.FromString(rows[0]["pb"]) if rows else None

    def list_assets(self) -> list[Asset]:
        return self._decode(self._rows("SELECT pb FROM assets ORDER BY asset_id"), Asset)

    # -- entities ----------------------------------------------------------

    def put_entity(self, entity: Entity) -> None:
        self._write(
            "INSERT INTO entities (entity_id, entity_class, first_seen, last_seen, pb) "
            "VALUES (?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET "
            "entity_class=excluded.entity_class, last_seen=excluded.last_seen, pb=excluded.pb",
            (
                entity.entity_id,
                entity.entity_class,
                to_epoch(entity.first_seen),
                to_epoch(entity.last_seen),
                entity.SerializeToString(),
            ),
        )

    def get_entity(self, entity_id: str) -> Entity | None:
        rows = self._rows("SELECT pb FROM entities WHERE entity_id=?", (entity_id,))
        return Entity.FromString(rows[0]["pb"]) if rows else None

    def list_entities(self, limit: int = 500) -> list[Entity]:
        return self._decode(
            self._rows("SELECT pb FROM entities ORDER BY last_seen DESC LIMIT ?", (limit,)), Entity
        )

    # -- observations ------------------------------------------------------

    def put_observation(self, obs: Observation) -> None:
        self._write(
            "INSERT OR REPLACE INTO observations (observation_id, entity_id, asset_id, ts, pb) "
            "VALUES (?,?,?,?,?)",
            (
                obs.observation_id,
                obs.entity_id,
                obs.asset_id,
                to_epoch(obs.timestamp),
                obs.SerializeToString(),
            ),
        )

    def list_observations(self, entity_id: str | None = None, limit: int = 200) -> list[Observation]:
        if entity_id:
            rows = self._rows(
                "SELECT pb FROM observations WHERE entity_id=? ORDER BY ts DESC LIMIT ?",
                (entity_id, limit),
            )
        else:
            rows = self._rows("SELECT pb FROM observations ORDER BY ts DESC LIMIT ?", (limit,))
        return self._decode(rows, Observation)

    # -- tracks ------------------------------------------------------------

    def put_track(self, track: Track) -> None:
        self._write(
            "INSERT INTO tracks (track_id, entity_id, state, updated, pb) VALUES (?,?,?,?,?) "
            "ON CONFLICT(track_id) DO UPDATE SET entity_id=excluded.entity_id, "
            "state=excluded.state, updated=excluded.updated, pb=excluded.pb",
            (track.track_id, track.entity_id, int(track.state), epoch_now(), track.SerializeToString()),
        )

    def get_track(self, track_id: str) -> Track | None:
        rows = self._rows("SELECT pb FROM tracks WHERE track_id=?", (track_id,))
        return Track.FromString(rows[0]["pb"]) if rows else None

    def list_tracks(self, states: Sequence[int] | None = None, limit: int = 500) -> list[Track]:
        if states:
            marks = ",".join("?" * len(states))
            rows = self._rows(
                f"SELECT pb FROM tracks WHERE state IN ({marks}) ORDER BY updated DESC LIMIT ?",
                (*states, limit),
            )
        else:
            rows = self._rows("SELECT pb FROM tracks ORDER BY updated DESC LIMIT ?", (limit,))
        return self._decode(rows, Track)

    def track_updated_at(self, track_id: str) -> float:
        rows = self._rows("SELECT updated FROM tracks WHERE track_id=?", (track_id,))
        return float(rows[0]["updated"]) if rows else 0.0

    # -- tasks -------------------------------------------------------------

    def put_task(self, task: Task) -> None:
        self._write(
            "INSERT INTO tasks (task_id, asset_id, status, updated, pb) VALUES (?,?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET asset_id=excluded.asset_id, "
            "status=excluded.status, updated=excluded.updated, pb=excluded.pb",
            (task.task_id, task.asset_id, int(task.status), epoch_now(), task.SerializeToString()),
        )

    def get_task(self, task_id: str) -> Task | None:
        rows = self._rows("SELECT pb FROM tasks WHERE task_id=?", (task_id,))
        return Task.FromString(rows[0]["pb"]) if rows else None

    def list_tasks(self, asset_id: str | None = None, limit: int = 200) -> list[Task]:
        if asset_id:
            rows = self._rows(
                "SELECT pb FROM tasks WHERE asset_id=? ORDER BY updated DESC LIMIT ?", (asset_id, limit)
            )
        else:
            rows = self._rows("SELECT pb FROM tasks ORDER BY updated DESC LIMIT ?", (limit,))
        return self._decode(rows, Task)

    def list_tasks_in_states(self, states: Sequence[int]) -> list[Task]:
        marks = ",".join("?" * len(states))
        return self._decode(
            self._rows(f"SELECT pb FROM tasks WHERE status IN ({marks})", tuple(states)), Task
        )

    # -- zones, missions, relationships ------------------------------------

    def put_zone(self, zone: Zone) -> None:
        self._write(
            "INSERT INTO zones (zone_id, name, pb) VALUES (?,?,?) ON CONFLICT(zone_id) "
            "DO UPDATE SET name=excluded.name, pb=excluded.pb",
            (zone.zone_id, zone.name, zone.SerializeToString()),
        )

    def get_zone(self, zone_id: str) -> Zone | None:
        rows = self._rows("SELECT pb FROM zones WHERE zone_id=?", (zone_id,))
        return Zone.FromString(rows[0]["pb"]) if rows else None

    def list_zones(self) -> list[Zone]:
        return self._decode(self._rows("SELECT pb FROM zones ORDER BY name"), Zone)

    def put_mission(self, mission: Mission) -> None:
        self._write(
            "INSERT INTO missions (mission_id, pb) VALUES (?,?) ON CONFLICT(mission_id) "
            "DO UPDATE SET pb=excluded.pb",
            (mission.mission_id, mission.SerializeToString()),
        )

    def list_missions(self) -> list[Mission]:
        return self._decode(self._rows("SELECT pb FROM missions"), Mission)

    def put_relationship(self, rel: Relationship) -> None:
        self._write(
            "INSERT OR REPLACE INTO relationships "
            "(relationship_id, subject_id, predicate, object_id, ts, pb) VALUES (?,?,?,?,?,?)",
            (
                rel.relationship_id,
                rel.subject_id,
                rel.predicate,
                rel.object_id,
                to_epoch(rel.timestamp),
                rel.SerializeToString(),
            ),
        )

    def list_relationships(self, subject_id: str | None = None, limit: int = 200) -> list[Relationship]:
        if subject_id:
            rows = self._rows(
                "SELECT pb FROM relationships WHERE subject_id=? OR object_id=? "
                "ORDER BY ts DESC LIMIT ?",
                (subject_id, subject_id, limit),
            )
        else:
            rows = self._rows("SELECT pb FROM relationships ORDER BY ts DESC LIMIT ?", (limit,))
        return self._decode(rows, Relationship)

    # -- entity identity resolution ----------------------------------------

    def resolve_entity(self, entity_id: str) -> str:
        """Map a possibly provisional entity identity to the canonical one."""
        rows = self._rows("SELECT canonical_id FROM entity_aliases WHERE alias_id=?", (entity_id,))
        return rows[0]["canonical_id"] if rows else entity_id

    def alias_entity(self, alias_id: str, canonical_id: str) -> None:
        if alias_id == canonical_id:
            return
        self._write(
            "INSERT OR REPLACE INTO entity_aliases (alias_id, canonical_id) VALUES (?,?)",
            (alias_id, canonical_id),
        )

    # -- events ------------------------------------------------------------

    def put_event(self, event: Event) -> None:
        self._write(
            "INSERT OR REPLACE INTO events "
            "(event_id, ts, severity, text, source, subject_kind, subject_id) VALUES (?,?,?,?,?,?,?)",
            (
                event.event_id,
                event.ts,
                event.severity,
                event.text,
                event.source,
                event.subject_kind,
                event.subject_id,
            ),
        )

    def list_events(self, limit: int = 100) -> list[Event]:
        rows = self._rows(
            "SELECT event_id, ts, severity, text, source, subject_kind, subject_id "
            "FROM events ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        return [Event(**dict(r)) for r in rows]

    # -- zone membership (for entry and exit detection) --------------------

    def zones_containing(self, track_id: str) -> set[str]:
        return {r["zone_id"] for r in self._rows("SELECT zone_id FROM zone_membership WHERE track_id=?", (track_id,))}

    def set_zone_membership(self, track_id: str, zone_ids: set[str]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM zone_membership WHERE track_id=?", (track_id,))
            self._conn.executemany(
                "INSERT INTO zone_membership (track_id, zone_id) VALUES (?,?)",
                [(track_id, z) for z in zone_ids],
            )
            self._conn.commit()


def new_event(text: str, severity: str, source: str, subject_kind: str = "", subject_id: str = "") -> Event:
    """Create an event with a fresh identifier and the current time."""
    return Event(
        event_id=new_id(),
        ts=epoch_now(),
        text=text,
        severity=severity,
        source=source,
        subject_kind=subject_kind,
        subject_id=subject_id,
    )


def json_dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"))
