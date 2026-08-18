# The Argus Engineering Knowledge Graph

This directory is the machine-readable truth about the Argus product itself:
what exists, what state it is in, what depends on what, what blocks what, and
why each decision was taken. It answers "what is happening inside the
codebase", never "what is happening in the physical world" (that is the
operational ontology in `link/` and the world models built on it; law 18
requires the two never mix).

The YAML here is the source. It is Git-reviewed like code. `STATUS.md` at the
repo root is generated from it; CI fails if they drift or if the graph
references anything that does not exist.

## Files

| File | Holds |
|---|---|
| `components.yaml` | Every engineering component, its maturity, disposition, tests, gaps, blockers, hardware evidence |
| `relationships.yaml` | Typed edges between components (USES, IMPLEMENTS, SUPERSEDES, ...) |
| `decisions.yaml` | Every decision, decided and open. Open decisions are founder-gated |
| `risks.yaml` | Live architectural risks, from the 17 Aug 2026 as-built audit onward |
| `research.yaml` | Research references mapped to the components and decisions they influence |
| `laws.yaml` | The architecture laws and where each is enforced (a test, a review step, or nowhere yet) |

## Maturity states (law 17: "built" has evidence levels)

One per component, strictly ordered by how much reality has touched it:

1. `planned` - intended, no code
2. `scaffolded` - code exists, not exercised (e.g. written but never run)
3. `simulated` - works, but only against simulated hardware or fixtures
4. `software_verified` - contract fully proven by software tests; needs no hardware to be real
5. `hardware_integrated` - verified running on or with the real target hardware
6. `field_validated` - proven in real operation outside the bench
7. `deprecated` - kept for reference, do not build on it

`hardware_integrated` and `field_validated` REQUIRE at least one entry in
`evidence.hardware_runs`. CI enforces this. Never promote a component's status
without the evidence to match; that is the whole point of the taxonomy.

## Disposition (the reconciliation verdict, 18 Aug 2026)

Every existing component carries the Keep / Refactor / Replace / Archive / New
classification from the architecture alignment:

- `keep` - sound in the target architecture; evolve in place
- `refactor` - right idea, wrong seam; reshape without losing behavior
- `replace` - will be superseded by a named successor (see `superseded_by`)
- `archive` - reference only; do not extend
- `new` - exists only in the target architecture, not yet built

## Working rules

- Update the graph in the same commit as the change it describes.
- Regenerate the status file afterward: `.venv/bin/python scripts/argus_graph.py status --write`
- Validate locally: `.venv/bin/python scripts/argus_graph.py validate`
- Query before large changes: `impact <id>` shows what depends on a component.
- An unresolved question is an entry in `decisions.yaml` with `status: open`,
  never an assumption in code.
