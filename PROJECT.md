# ARGUS: product context

For the target architecture read `ARCHITECTURE.md`. For current state read
`STATUS.md`. This file is orientation: what the product is, who it is for,
what the pieces are called, and what the words mean.

## The product

Argus is an autonomy operating system and fleet intelligence platform for
unmanned machines. Install the same runtime on any machine, a ground vehicle,
a drone, a vessel, a fixed sensor, and the fleet behaves as one coordinated
force commanded by a human through a map and voice, while every machine
remains fully capable alone when every link is gone.

Positioning: the contract and mesh layer of Anduril Lattice, the ontology and
decision layer of Palantir, and the onboard autonomy of Skydio, in one
sovereign, air-gapped stack. The moat is the ontology, the accumulated world
model, and the cognitive harness, never whichever model or sensor is popular
this quarter. Deployment targets are air-gapped; sovereignty is a law, not a
feature.

The name ARGUS OS covers the whole family, ground station and vehicle alike
(founder decision, 4 Aug 2026). The word itself is still a placeholder.

## Program phase (August 2026)

The v1 build plan (`ARGUS-OS-PLAN.md`, historical) delivered the contract,
the fleet world model, the operator app, the edge runtime above the drivers,
and voice, all software-verified or simulated. The 17 Aug 2026 as-built audit
and the architecture alignment (18 Aug 2026) reframed the program: before the
cognitive layer is built, the perception, localization, persistence, and
vehicle-control seams get corrected, and the runtime gets proven on the real
Jetson and the real UGV, behind a hard hardware safety gate. The roadmap is
`NEXT-STEPS.md`.

## The pieces

| Name | What it is | Where |
|---|---|---|
| ARGUS LINK | The frozen v1 contract: protobuf ontology and five wire messages | `link/` |
| ARGUS TRACK | Fleet world model server: ingest, fusion, zones, events, tasks | `track/` |
| ARGUS PILOT | The machine edge runtime: manifest boot, HAL, autonomy loop | `drive/pilot/` |
| ARGUS C2 | The operator application: map, force rail, events, voice bar | `c2/` |
| AI Gateway | Capability-based model access with policy profiles | `gateway/` |
| Voice | Push-to-talk, strict intents, readback confirmation | `voice/` |
| ARGUS DRIVE | The Land domain execution layer (target meaning; today the directory also holds PILOT and teleop) | `drive/` |
| ARGUS FLIGHT / SEA | Air and marine domain execution layers | planned |
| Cognitive Runtime | The machine-local harness: world model, memory, planning, verification, safety, skills | planned |
| Argus Sync | Local-first incremental sync between machines and fleet storage | planned |
| ARGUS INTEL | Product name for reports, Q&A, analytics; maps to gateway capabilities over world-model history, not a separate server | in voice Q&A today |
| Engineering Knowledge Graph | Machine-readable truth about the codebase itself | `docs/architecture/graph/` |
| ugv-01 | The first steel: a Jeep-chassis 4x4 electric UGV with a Jetson AGX Orin 64GB | `bodies/ugv-01/` |

## Glossary

- **Asset**: a machine or sensor that is part of our force.
- **Entity**: anything in the world that is not our asset.
- **Observation**: one immutable report about an entity by one sensor at one time.
- **Track**: the fused live state of one entity; what operators see.
- **Zone / Mission / Task / Relationship**: see the ontology in `link/`.
- **Manifest**: the per-machine YAML declaring identity, limits, and drivers.
- **HAL**: the driver seam; nothing above it knows what hardware exists.
- **Provider / adapter / driver**: a replaceable implementation behind a typed interface (sensors, localization, models, transports alike).
- **Skill**: a typed capability request (navigate, patrol, inspect, return_home) executed by a domain layer.
- **Profile**: an AI policy profile (`deployed`, `dev`, `demo`); `deployed` is air-gapped and refuses cloud, fail-closed.
- **Waterline**: the line below which operators never see; internals stay under it.
- **Maturity**: the law-17 evidence level of a component (see `STATUS.md`).
- **Teleop**: manual driving through the cockpit and bridge; a permanent fallback capability, currently a parallel stack being converged onto the HAL.

## Working with this repository

Read `CLAUDE.md` first, always, and especially its rule zero if the checkout
might be on a vehicle. Founder gates are real: stages, frontend surfaces, and
open decisions do not resolve silently. The graph and STATUS.md are updated
in the same commit as the change they describe.
