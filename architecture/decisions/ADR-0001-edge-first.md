# ADR-0001: Edge-first autonomy

**Status:** accepted. **Date:** 2026-08-18 (records a principle in force
since the original plan's disconnection law, 2026-08-02).
**Affected:** every component; enforced today by `tests/test_pilot_loop.py`
and the gateway policy tests.

## Context

Argus deploys to air-gapped sites over unreliable links. Comparable platforms
quietly assume connectivity; a defence autonomy product cannot.

## Decision

The mission path runs entirely on the machine: perception, localization,
world state, task execution, safety, navigation, contingency, and
return-to-safe behavior require no cloud, no C2, and no link. Connectivity
enhances Argus; it never creates autonomy (laws 1 and 6 of the eighteen).
Machine-local truth is authoritative for local execution; TRACK is
authoritative for the fleet view; sync reconciles them with provenance.

## Alternatives considered

Cloud or ground-station-dependent autonomy (simpler, richer compute) fails
the disconnection and sovereignty laws outright. A hybrid "degraded local
mode" was rejected because behavior that differs when watched cannot be
trusted; the autonomy core deliberately never checks whether the link is up.

## Consequences

Every capability must be sized for the Jetson. The air-gapped model path must
be proven, not assumed (risk R-6). Local persistence becomes mandatory
(ADR-0005), because a machine that reboots into amnesia is not autonomous.
