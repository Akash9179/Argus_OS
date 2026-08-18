# ADR-0002: One cognitive architecture, many bodies

**Status:** accepted. **Date:** 2026-08-18, founder decision D-12; resolves
the plan-era open decision 7 (Drive/Flight product structure).
**Affected:** `core.cognitive_runtime`, `core.skills`, `domains.drive`,
`domains.flight`, `domains.sea`.

## Context

The schema law kept Land, Air, and Sea open since day one, but whether Drive
and a future Flight were one product line or two was explicitly undecided.
The alignment discussion and the world-task factorization research (R6)
settled it.

## Decision

There is one Argus cognitive runtime and one ontology across all domains.
Argus Drive, Argus Flight, and Argus Sea are domain execution layers: they
know how their embodiment performs a requested skill (`return_home` is path
planning and braking on land, a 3D route and flight controller in the air,
heading and thrust at sea). No domain branch exists above the skill boundary;
the runtime reasons in goals and capabilities. Contingency policy is common
in principle and domain-specific in physical response, as data.

## Alternatives considered

Independent Land/Air/Sea brains: triple maintenance, divergent safety
stories, and no shared learning. A single monolithic model as the brain:
fails laws 4 and 12 and the replaceability principle.

## Consequences

The skill contract must be designed before Flight exists, and the domain
acceptance test (same skill request, different execution provider) becomes
the proof. ARGUS DRIVE's name narrows to the Land execution layer; the
`drive/` directory currently holds more than that, tracked by OD-17.
