"""Identifier and timestamp helpers.

All identifiers in the system are ULIDs and all timestamps are UTC, per the
ontology. These helpers are the only place either is produced, so the rule
cannot drift.
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.protobuf.timestamp_pb2 import Timestamp
from ulid import ULID


def new_id() -> str:
    """A fresh ULID as its 26-character string form."""
    return str(ULID())


def now() -> datetime:
    """The current time, always timezone-aware UTC."""
    return datetime.now(timezone.utc)


def now_ts() -> Timestamp:
    """The current time as a protobuf Timestamp."""
    ts = Timestamp()
    ts.FromDatetime(now())
    return ts


def to_epoch(ts: Timestamp) -> float:
    """Seconds since the Unix epoch for a protobuf Timestamp. 0.0 if unset."""
    if not ts.seconds and not ts.nanos:
        return 0.0
    return ts.seconds + ts.nanos / 1e9


def epoch_now() -> float:
    """Current time as seconds since the Unix epoch."""
    return now().timestamp()
