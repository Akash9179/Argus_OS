# ADR-0008: The Engineering Knowledge Graph

**Status:** accepted (implemented 2026-08-18). **Date:** 2026-08-18.
**Affected:** `engineering.graph`, `STATUS.md`. Implements laws 17 and 18.

## Context

The repository reached the size where architecture drift is a product risk:
five documents could each claim a different "what is done", and the audit
found the docs already contradicting each other (CLAUDE.md said no Jetson had
run anything while STATUS.md recorded the relay proof). The alignment also
demands maturity honesty: simulated software was one checkbox away from
reading as hardware-proven.

## Decision

A machine-readable engineering graph, separate from the operational ontology
(they never share a database), stored repo-native and Git-reviewed:

- `architecture/graph/*.yaml`: components (with maturity, disposition,
  tests, gaps, blockers, hardware evidence), relationships, decisions,
  risks, research, laws.
- `scripts/argus_graph.py`: validator and query CLI (validate, status,
  incomplete, blockers, component, impact, untested, hardware-unvalidated,
  decisions, risks), and the generator for `STATUS.md`.
- `tests/test_engineering_graph.py` in the fast CI suite: dangling
  references, nonexistent paths, maturity claims without evidence, planned
  components claiming code, unowned top-level directories, and STATUS.md
  drift all fail the build.

`STATUS.md` is generated, never hand-edited. The graph is updated in the
same commit as the change it describes. Claude queries `impact <id>` before
large changes.

## Alternatives considered

Neo4j or another graph database: operational overhead with no reviewer
visibility; the YAML is diffable in review, which is most of the value. A
generated database (`var/engineering_graph.db`) stays open as a later
addition once query needs outgrow the CLI. Hand-maintained STATUS.md:
that is the drift this ADR exists to end.

## Consequences

"What is still only simulated", "what has never run on Jetson", "what breaks
if LocalizationProvider changes" are now commands, not archaeology. The cost
is discipline: code changes that alter a component's state must touch the
graph, and CI makes forgetting expensive rather than silent.
