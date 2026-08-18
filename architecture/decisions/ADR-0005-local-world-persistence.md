# ADR-0005: Persistent local world store

**Status:** accepted-direction (not yet implemented). **Date:** 2026-08-18.
**Affected:** `edge.worldslice` (superseded), `core.local_world_model`,
`platform.sync`, `learning.experience`. Closes risk R-10; implements law 15.

## Context

All machine-local state (WorldSlice entities, current task, home) is in
memory and dies with the process. A reboot is amnesia, which is incompatible
with unattended deployment, with law 15, and with any learning pipeline.

## Decision

Every machine gets a persistent Local World Model backed by:

1. **A structured store**, SQLite in WAL mode at `var/argus_local.db` unless
   profiling proves otherwise, holding identity, configuration snapshots,
   missions, tasks and their history, entities and relationships, plans,
   decisions, action records, memory items, safe locations, sync cursors,
   and software/model state.
2. **An append-only event journal** for decisions and state transitions,
   giving replay, causal reconstruction, sync (cursor-based, see Argus
   Sync), and learning datasets. Exact format is OD-16.
3. **File-based heavy recordings** (MCAP/rosbag, SVO) with indexed metadata;
   large blobs never live in the relational store.

Reboot behavior: load identity, configuration, last safe/home state, and the
unfinished task; replay the journal past the last snapshot; validate sensors
and controllers; then decide whether the task may safely resume. **A machine
never automatically resumes physical motion because a task was RUNNING before
reboot.** Absent a safe resume, it enters the configured contingency state.

## Alternatives considered

Postgres or a graph database: heavier than one machine needs, and law 18's
"the model is a graph" does not require a graph database. Periodic full-state
snapshots only: loses the causal record the learning plane and provenance law
need.

## Consequences

TRACK's storage pattern (protobuf blobs plus lifted columns, single-writer
asyncio) is the proven in-house reference. The reboot acceptance test in
ARCHITECTURE.md section 8 becomes implementable. Sync (phase 8) reads the
journal through cursors instead of re-uploading state.
