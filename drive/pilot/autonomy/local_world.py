"""What a machine remembers across a reboot.

The offline truth law (law 15) says a reboot must not be amnesia: identity,
home, the current order, and the machine's own memory of what it has seen
survive a process restart. This is that store (ADR-0005): one SQLite file
in WAL mode, written through as state changes so a power cut loses nothing
that had happened, plus an append-only journal of decisions and state
transitions.

The journal has no update and no delete, and that absence is deliberate.
It is the causal record: replay, sync (cursor-based, ADR-0005), and the
learning plane all read it, and a past that could be rewritten would be a
lie told to every one of them. Storage format is open decision OD-16; this
is its default direction (SQLite WAL for structured state), so a different
answer there changes this file and nothing above it.

The task is stored as its raw protobuf bytes, the same choice TRACK made
and for the same reason: protobuf preserves fields a newer sender included
that this build does not know about, so an older runtime never destroys a
newer server's data across a reboot.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from link.v1.ontology_pb2 import Task

SCHEMA = """
CREATE TABLE IF NOT EXISTS identity (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    asset_id TEXT NOT NULL, name TEXT NOT NULL, asset_class TEXT NOT NULL,
    first_boot REAL NOT NULL, boot_count INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS home (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    latitude_deg REAL NOT NULL, longitude_deg REAL NOT NULL,
    set_at REAL NOT NULL);

CREATE TABLE IF NOT EXISTS current_task (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    task_id TEXT NOT NULL, pb BLOB NOT NULL, updated REAL NOT NULL);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY, entity_class TEXT NOT NULL,
    latitude_deg REAL NOT NULL, longitude_deg REAL NOT NULL,
    last_seen REAL NOT NULL, times_seen INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS journal (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
"""


@dataclass
class JournalEntry:
    """One thing that happened, recorded when it happened."""

    seq: int
    ts: float
    kind: str
    detail: dict


class LocalStore:
    """The machine's persistent local truth. Safe to call from any thread."""

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

    def _write(self, sql: str, params: Sequence) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _rows(self, sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    # -- identity ----------------------------------------------------------

    def record_boot(self, asset_id: str, name: str, asset_class: str) -> int:
        """Count this boot and keep who the machine is. Returns the count.

        A store that already belongs to a different asset identity is
        journaled, never silently overwritten: the history in here was
        earned under the old name and stays attributed to it.
        """
        with self._lock:
            rows = self._rows("SELECT asset_id, boot_count FROM identity WHERE id=1")
            if rows and rows[0]["asset_id"] != asset_id:
                self.append(
                    "identity_changed", previous=rows[0]["asset_id"], asset_id=asset_id
                )
            count = (rows[0]["boot_count"] + 1) if rows else 1
            self._write(
                "INSERT INTO identity (id, asset_id, name, asset_class, first_boot, boot_count) "
                "VALUES (1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "asset_id=excluded.asset_id, name=excluded.name, "
                "asset_class=excluded.asset_class, boot_count=excluded.boot_count",
                (asset_id, name, asset_class, time.time(), count),
            )
            self.append("boot", asset_id=asset_id, boot_count=count)
            return count

    def identity(self) -> dict | None:
        rows = self._rows(
            "SELECT asset_id, name, asset_class, first_boot, boot_count FROM identity WHERE id=1"
        )
        return dict(rows[0]) if rows else None

    # -- home --------------------------------------------------------------

    def home(self) -> tuple[float, float] | None:
        rows = self._rows("SELECT latitude_deg, longitude_deg FROM home WHERE id=1")
        return (rows[0]["latitude_deg"], rows[0]["longitude_deg"]) if rows else None

    def set_home(self, latitude_deg: float, longitude_deg: float) -> None:
        self._write(
            "INSERT INTO home (id, latitude_deg, longitude_deg, set_at) VALUES (1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET latitude_deg=excluded.latitude_deg, "
            "longitude_deg=excluded.longitude_deg, set_at=excluded.set_at",
            (latitude_deg, longitude_deg, time.time()),
        )

    def clear_home(self) -> None:
        self._write("DELETE FROM home WHERE id=1", ())

    # -- the current order -------------------------------------------------

    def current_task(self) -> Task | None:
        rows = self._rows("SELECT pb FROM current_task WHERE id=1")
        return Task.FromString(rows[0]["pb"]) if rows else None

    def set_current_task(self, task: Task | None) -> None:
        if task is None:
            self._write("DELETE FROM current_task WHERE id=1", ())
            return
        self._write(
            "INSERT INTO current_task (id, task_id, pb, updated) VALUES (1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET task_id=excluded.task_id, "
            "pb=excluded.pb, updated=excluded.updated",
            (task.task_id, task.SerializeToString(), time.time()),
        )

    # -- entities ----------------------------------------------------------

    def save_entity(
        self,
        entity_id: str,
        entity_class: str,
        latitude_deg: float,
        longitude_deg: float,
        last_seen: float,
        times_seen: int,
    ) -> None:
        self._write(
            "INSERT INTO entities "
            "(entity_id, entity_class, latitude_deg, longitude_deg, last_seen, times_seen) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET "
            "latitude_deg=excluded.latitude_deg, longitude_deg=excluded.longitude_deg, "
            "last_seen=excluded.last_seen, times_seen=excluded.times_seen",
            (entity_id, entity_class, latitude_deg, longitude_deg, last_seen, times_seen),
        )

    def forget_entity(self, entity_id: str) -> None:
        self._write("DELETE FROM entities WHERE entity_id=?", (entity_id,))

    def entities(self) -> list[sqlite3.Row]:
        return self._rows(
            "SELECT entity_id, entity_class, latitude_deg, longitude_deg, "
            "last_seen, times_seen FROM entities"
        )

    # -- the journal -------------------------------------------------------

    def append(self, kind: str, **detail) -> None:
        """One more thing that happened. There is no way to take it back."""
        self._write(
            "INSERT INTO journal (ts, kind, detail) VALUES (?,?,?)",
            (time.time(), kind, json.dumps(detail, separators=(",", ":"))),
        )

    def journal(self, after_seq: int = 0, limit: int = 1000) -> list[JournalEntry]:
        """Entries in order, resumable from a cursor the caller keeps."""
        rows = self._rows(
            "SELECT seq, ts, kind, detail FROM journal WHERE seq > ? ORDER BY seq LIMIT ?",
            (after_seq, limit),
        )
        return [
            JournalEntry(
                seq=r["seq"], ts=r["ts"], kind=r["kind"], detail=json.loads(r["detail"])
            )
            for r in rows
        ]
