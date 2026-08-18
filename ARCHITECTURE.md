# ARGUS Architecture

**Canonical target architecture. Adopted 18 August 2026 on founder instruction
(decision D-12), distilled from `ARGUS_ARCHITECTURE_ALIGNMENT_REPORT.md`,
which remains the full-depth source document.** Where any other document in
this repository disagrees with this one on direction, this one wins. Where
this document disagrees with the code on what exists, the code wins: this file
states where we are going, the Engineering Knowledge Graph
(`docs/architecture/graph/`) and `STATUS.md` state where we are, and ADRs
(`docs/architecture/decisions/`) record why and where we deviated.

## 1. What Argus is

Argus OS is a modular, edge-native autonomy platform for unmanned machines
across Land, Air, and Sea. Each machine perceives through replaceable sensors,
represents reality through a shared ontology, keeps persistent local world
state and memory, reasons through a model-agnostic cognitive harness, verifies
and executes typed skills through domain-specific controllers, stays safe and
autonomous when disconnected, synchronizes into a Maven-like fleet
intelligence layer when connected, and improves through a controlled
experience, simulation, and learning pipeline.

One brain architecture, many bodies. Argus Drive, Argus Flight, and Argus Sea
are domain execution layers that know how a particular embodiment performs a
requested skill. They are not separate brains, and there is no domain branch
above the skill boundary. The cognitive runtime reasons in goals and
capabilities, never in wheel PWM or rotor RPM.

The enduring product is the ontology, the world model, memory, the cognitive
harness, skills, safety, experience, fleet intelligence, and the hardware and
model abstractions. Everything else, every sensor, every model, every compute
board, every vehicle, is replaceable. Do not optimize for more AI; optimize
for modularity, truth, replaceability, local autonomy, typed interfaces,
observability, safety, testability, provenance, and controlled learning.

## 2. The eighteen laws

Laws 1 to 10 are the original ten and bind exactly as they always have. Laws
11 to 18 were added by the alignment. Violating one is an architecture bug
even if the code works. Enforcement per law is tracked in
`docs/architecture/graph/laws.yaml`; a law marked `gap` there is guarded by review
alone until its enforcement point exists.

1. **HAL law.** No vehicle, sensor, or device specifics above the HAL. All
   body differences live in drivers, providers, and capability manifests.
2. **SDK honesty law.** Applications use only public service interfaces. C2
   must never use an interface a third-party application could not.
3. **Gateway law.** No model or provider names outside the AI gateway.
   Providers are swappable adapters behind capability interfaces.
4. **Schema law.** The ontology is multi-domain from the first line; ground is
   merely implemented first. Adding a domain adds subtypes and drivers, never
   skeleton changes.
5. **Waterline law.** Operators never see internals. Map, plain sentences,
   voice. Every operator-facing string lives in data, not code.
6. **Disconnection law.** Every asset is fully functional alone. Connectivity
   adds capability; it never enables basic operation. Nothing in a mission
   path may require cloud, C2, or any link.
7. **Honesty law.** Never claim more certainty than held. Confidence is
   surfaced in language; spoken output is always also printed.
8. **Sovereignty laws.** Deployment targets are air-gapped. No Chinese-origin
   AI models anywhere in a deployed profile, and check the backbone every
   time, not the badge. Cloud adapters exist only in dev and demo profiles. An
   unapproved model fails closed.
9. **Licensing law.** Every third-party model, library, and dataset is
   license-verified for military use before integration, recorded in
   `LICENSES.md`. When in doubt, flag and ask.
10. **Registry law.** Everything the HAL knows is queryable structured data.
11. **One cognitive architecture.** Land, Air, and Sea share one cognitive
    runtime and one ontology. Domain-specific behavior belongs below the
    skill boundary.
12. **Bounded actuation law.** A model may propose a plan, a typed action, a
    skill invocation, or parameters within bounded schemas. It must never
    directly generate motor or relay commands. Every physical action passes
    through action verification, the safety governor, a skill, a domain
    controller, and a hardware driver, in that order, and higher intelligence
    can never bypass a lower safety layer.
13. **Controlled learning law.** No uncontrolled self-modification in the
    field. In-mission adaptation is replanning and memory, never weight
    changes. Improvements flow through experience, training or simulation,
    evaluation, safety regression, approval and signing, then deployment.
14. **No snowflake machines.** SSH is for debugging. Every permanent fix
    returns to Git, tests, a versioned release, and deployment. Claude Code
    is a development and maintenance tool, never a runtime dependency.
15. **Offline truth law.** Every machine keeps enough persistent local state
    to recover identity, mission, home and safe state, configuration, and
    relevant memory after a process restart or reboot. A reboot must not be
    amnesia, and a machine must never automatically resume physical motion
    just because a task was RUNNING before the reboot.
16. **Provenance law.** Argus can always answer: which sensor produced this
    observation, when, on which machine, with what confidence, which model
    transformed it, which decision used it, which action followed, and which
    software and model versions were running.
17. **Evidence law.** "Built" has evidence levels: `planned`, `scaffolded`,
    `simulated`, `software_verified`, `hardware_integrated`,
    `field_validated`, `deprecated`. Nothing is plainly "done", and a
    maturity promotion without matching evidence is a lie the CI rejects.
18. **Queryable architecture law.** The codebase has a machine-readable
    engineering graph answering what exists, what is incomplete, what depends
    on what, what tests cover it, what hardware validated it, and what blocks
    it. The engineering graph and the operational ontology never share a
    database.

## 3. Target system architecture

```text
                                HUMAN / OPERATOR
                                       |
+---------------------------------------------------------------------------+
|                                ARGUS C2                                   |
|  Map | Missions | Fleet health | Natural language | Brain state | Diag    |
|  Maven-like fleet intelligence | Manual / Assisted / Autonomous control   |
+------------------------------------+--------------------------------------+
                                     |  ARGUS LINK (connection may be absent)
                                ARGUS TRACK
                          fleet world model + sync
                                     |
          +--------------------------+--------------------------+
          |                          |                          |
     LAND MACHINE               AIR MACHINE                SEA MACHINE
          |                          |                          |
          +-------- EACH MACHINE RUNS LOCALLY (ARGUS OS) -------+
                                     |
|---------------------------------------------------------------------------|
|                 ARGUS COGNITIVE RUNTIME / HARNESS                         |
|   PERCEIVE -> UNDERSTAND -> REMEMBER -> IMAGINE -> DECIDE                 |
|        -> VERIFY -> ACT -> OBSERVE -> ADAPT                               |
|---------------------------------------------------------------------------|
|                      LOCAL WORLD MODEL (persistent)                       |
|   ontology objects | relations | mission | confidence | provenance        |
|---------------------------------------------------------------------------|
|      MEMORY            REASONING (Model Gateway)          PLANNER         |
|---------------------------------------------------------------------------|
|                          ACTION VERIFIER                                  |
|                          SAFETY GOVERNOR                                  |
|                           SKILL LIBRARY                                   |
|---------------------------------------------------------------------------|
                                     |
                       DOMAIN EXECUTION LAYER
              ARGUS DRIVE   |   ARGUS FLIGHT   |   ARGUS SEA
                                     |
                  HARDWARE / DEVICE ABSTRACTION (HAL)
        PERCEPTION providers | LOCALIZATION providers | CONTROL drivers
        ZED / thermal / ...  | GNSS / IMU / VSLAM     | MCU / CAN / motors
```

Four surrounding planes:

- **Fleet plane:** local world models -> LINK -> TRACK -> fleet ontology -> C2.
- **Learning plane:** mission experience -> datasets -> Isaac Sim / Isaac Lab
  -> evaluation -> signed policy or model release -> devices. The Jetson runs
  inference; training does not happen on field machines.
- **Operations plane:** Git -> CI -> versioned release -> Ansible/SSH today,
  signed releases, private registry, staged rollout and rollback later.
- **Engineering plane:** code + manifests + tests + ADRs + research +
  releases -> the Engineering Knowledge Graph -> generated STATUS,
  dependency and impact queries.

Boundary rules that keep this honest:

- **ZED is the eyes, never the brain.** Use Stereolabs capabilities behind a
  ZED adapter implementing the Argus perception interface. A different camera
  is a different adapter behind the same interface.
- **Perception is typed streams, not just Detections.** Frame, depth, point
  cloud, IMU, GNSS, detection, track, semantic, occupancy streams, with
  per-sensor discoverable capabilities. Not every sensor provides every
  stream. High-rate data stays on a local sensor bus; LINK carries semantic
  messages; a recording pipeline captures selected raw experience.
- **Localization is a first-class provider.** GNSS, IMU, VSLAM, and wheel
  odometry fuse behind a `LocalizationProvider` producing a `PoseEstimate`
  with frame, covariance, source contributions, health, and confidence. The
  rest of Argus never knows which provider is active.
- **Local truth is authoritative for local execution; TRACK is authoritative
  for the fleet view.** A machine never needs TRACK to decide. Sync preserves
  origin, timestamps, confidence, provisional identity, and conflict history.
- **Transport is a capability.** MQTT is one comms provider. The runtime
  reacts to communication state, never to a particular radio.
- **Models are registry entries.** Every deployable model records provider,
  family, version, origin country, license, weights hash, quantization,
  capabilities, approved profiles, and benchmark evidence. Fails closed.

## 4. The Cognitive Runtime

The missing heart of the target system, and deliberately not one LLM. It is
the harness connecting perception, ontology, world state, memory, models,
planners, skills, verification, safety, execution, and feedback:
EventBus, WorldModelClient, MemoryManager, Executive, ModelGateway, Planner,
ActionVerifier, ContingencyManager, SkillRegistry, SkillExecutor,
ExplanationRecorder.

Rules that survive any implementation choice:

- **Deterministic first.** The runtime is built and tested with no model at
  all; a dead model degrades cognition, never the mission (the no-model
  acceptance test in section 8).
- **No free-chat agent swarm.** Bounded specialist roles over one shared
  world state, invoked through typed tool contracts, with explicit ownership.
- **Typed plans only.** Models output schemas (goal, steps as skill
  invocations, assumptions, constraints, contingencies, confidence), never
  prose for execution.
- **Verification before actuation.** The ActionVerifier checks a proposed
  action against the stated plan, skill availability, parameter limits, the
  ontology, the mission, current world state, and the safety governor.
  Rejection leads to replan, operator review, or contingency.
- **Contingency is configurable policy, not a hard-coded reflex.** The
  founder requirement stands: an uncertain machine that cannot safely
  continue returns to its safe or home state. The safe physical response is
  domain-specific (a UAV does not "pull over"), so it is data, per domain and
  per failure mode.
- **Memory has timescales.** Working and sensory (seconds to minutes),
  episodic (mission events), semantic (compressed reusable knowledge with
  provenance and confidence; one-off anecdotes never silently become truth),
  and fleet memory via sync.
- **Every important decision leaves an explanation record**: trigger, inputs,
  selected plan, reason codes, confidence, verifier and safety verdicts, and
  versions. Operational rationale, not hidden chain-of-thought. C2 surfaces
  it as the Brain State view.

## 5. Reconciliation: as-built to target

Full per-component verdicts live in the graph (`disposition` field); this is
the shape of it. Argus is not rebuilt from scratch.

**Keep (evolve in place):** LINK and its frozen v1 discipline, TRACK, C2, the
AI gateway (it grows into the Model Gateway), voice, the HAL framework with
manifests, registry, and loader, the edge LINK client with its offline queue,
the simulated vehicle fixture, PILOT and its autonomy loop, the teleop
watchdog, the install tooling.

**Refactor (right idea, wrong seam):** the LocomotionDriver interface loses
`pose()` to the LocalizationProvider; the AutonomyCore splits into Skills and
Executive logic inside the Cognitive Runtime (OD-14); the teleop bridge and
cockpit converge onto the HAL so exactly one process owns physical control
(ADR-0009); ARGUS DRIVE narrows to mean the Land execution layer.

**Replace (named successor exists in the graph):** the Detection-only
SensorDriver seam is superseded by the perception stream interfaces, behind a
compatibility shim during migration; the memory-only WorldSlice is superseded
by the persistent Local World Model.

**Archive (reference, do not extend):** the `drive/brain/` prototype. Its
bounded-intent and human-override patterns inform the Cognitive Runtime; its
direct SDK call and hardcoded model name die with it.

**New:** the Cognitive Runtime and its parts (memory, verifier, safety
governor, skills), the Local World Model, the perception interfaces, the
LocalizationProvider, the ZED and detector providers, Argus Sync, the
learning plane, fleet deployment, Flight and Sea domains, and the Engineering
Knowledge Graph (built 18 Aug 2026).

Priority order is deliberate: fix the boundaries around perception,
localization, local persistence, and vehicle control **before** adding a
large cognitive layer on top. A brain trained on fake senses and fake body
interfaces makes the software look advanced while delaying the hardest truth,
whether the machine can reliably observe, localize, and act.

## 6. The safety gate (hard gate, not preference)

The real vehicle, as surveyed 11 August 2026: the deployed MCU firmware holds
its last throttle command forever on link loss; the steering feedback sensor
is disconnected, so held steering commands run the actuator into its
mechanical stop; both brake relays are disconnected; there is no ignition or
e-stop relay. The v4 replacement firmware with a latching watchdog and
break-before-make relay logic is written but has never been flashed or
bench-verified, and the relay map itself is verbal and unverified.

Therefore: **no autonomous moving-hardware test of any kind until the relay
map is bench-verified (wheels off the ground, one relay at a time) and the
low-level fail-safe path is proven on the bench.** Nothing in Argus software
can currently make this vehicle safe; the fix is at the firmware and bench
level. Re-verify the current physical state before every hardware session,
because this paragraph describes August 2026, not necessarily today. The
repository-level rule zero in `CLAUDE.md` (never actuate from a vehicle
checkout without explicit human confirmation) stands above everything here.

## 7. Source-of-truth hierarchy

```text
ARCHITECTURE.md                      target architecture and the 18 laws
ARGUS_ARCHITECTURE_ALIGNMENT_REPORT  full-depth source of the target (17 Aug 2026)
docs/architecture/decisions/ADR-*.md      decisions and deviations, with context
docs/architecture/graph/*.yaml            machine-readable component/status/dependency truth
docs/architecture/audits/                 point-in-time audits (2026-08-17 as-built)
STATUS.md                            generated implementation state (never hand-edited)
NEXT-STEPS.md                        prioritized, dependency-aware execution plan
CLAUDE.md                            instructions for AI coding agents
PROJECT.md                           product context and glossary
RESEARCH.md                          research mapped to architecture decisions
ARGUS-OS-PLAN.md                     historical: the v1 build plan (stages 1 to 5) and
                                     its decisions record; superseded on direction by
                                     this file, still binding where it records founder
                                     decisions not yet migrated elsewhere
LICENSES.md                          license verdicts (law 9)
INSTALL.md                           agent-executable install for the current stack
```

When documents disagree: code and hardware evidence define as-built truth;
this file defines target direction; ADRs explain deliberate deviations; the
graph and STATUS.md state the current gap. `MODELS.md`, `DEPLOYMENT.md`, and
`SECURITY.md` are planned and will be created when their first real content
exists (the model registry, the Ansible inventory, the security controls),
not before; empty documents are drift waiting to happen.

## 8. Acceptance tests for the architecture itself

These test whether the architecture is real, not whether features work. Each
becomes an automated test as its subject matures; until then it is the review
standard.

- **Replace-camera test:** swap the ZED provider for a simulated or alternate
  provider; runtime, world model, planner, and C2 are unchanged.
- **Replace-model test:** swap a model provider; only adapter and config
  change.
- **Disconnect test:** cut communication mid-mission; the safe mission
  continues, events queue, C2 marks the machine disconnected, reconnect
  merges. (Already CI-proven at the task level.)
- **Reboot test:** restart the edge runtime mid-mission; identity, config,
  home, and world state recover; the unfinished task is evaluated; no blind
  automatic motion.
- **Domain test:** the same logical skill request runs against Land and a
  simulated Air; the request is common, only the execution provider differs.
- **No-model test:** kill the local LLM/VLM; deterministic autonomy, safety,
  and navigation still work; the system reports degraded cognition.
- **Bad-model-action test:** a model proposes an unavailable or unsafe
  action; the ActionVerifier rejects it and no hardware action occurs.
- **Graph consistency test:** delete or rename a declared component; CI
  detects the dangling edge. (Live today: `tests/test_engineering_graph.py`.)
- **Evidence test:** a component cannot claim `hardware_integrated` without
  linked hardware evidence. (Live today.)

## 9. Sequencing

The dependency-aware plan with checklists and acceptance criteria lives in
`NEXT-STEPS.md`. The order of the campaign, from the alignment: re-audit and
the safety gate; this document hierarchy and graph; the three seam fixes
(perception streams, localization provider, persistent local store) plus
teleop convergence; real Jetson edge proof with ZED and safe UGV navigation
and experience recording; only then the Cognitive Runtime v1,
deterministic-first; then model evaluation on the Orin, memory and
prediction, Maven-like C2, Argus Sync, the learning plane, fleet deployment,
and Air/Sea expansion after the universal boundaries have survived real Land
hardware.

What not to build, ever: a giant monolithic AI brain owning perception,
truth, safety, and control; three independent operating systems; rewrites of
strong vendor capabilities (stereo depth, physics simulation, generic RL
infrastructure, Jetson base OTA) without measured cause; raw sensor streams
in the fleet ontology by default; a C2 that local execution needs; permanent
device-only fixes; or new architecture files that duplicate existing truth.
