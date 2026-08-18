"""What happened at the wheel, who did it, and when.

The daemon had no memory: after an incident there was nothing to read
back (risk R-8). This is the fix (ADR-0009): one JSON line per event,
appended as it happens and flushed before the call returns, so the last
line on disk is the last thing that happened even if the process dies
mid-session.

Events record transitions, not traffic. Fifty command frames a second
would bury the story; armed, latched, re-armed, ignition, preflight and
session boundaries ARE the story. Secrets never appear in an event: a
failed auth is recorded as the fact of a failure, not the token that
failed.

Timestamps are wall clock, because an incident review correlates this
file with people's memories and other systems' logs, and those speak in
clock time, not process uptime.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class SessionLog:
    """Append-only JSONL. Safe to call from any daemon thread."""

    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._file = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self.path, "a", encoding="utf-8")

    def event(self, event: str, session: str | None = None, **detail) -> None:
        if self._file is None:
            return
        record: dict = {"ts": time.time(), "event": event}
        if session is not None:
            record["session"] = session
        record.update(detail)
        line = json.dumps(record, separators=(",", ":"))
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None


def read_events(path: str | Path) -> list[dict]:
    """Every event in the file, in the order it was written."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
