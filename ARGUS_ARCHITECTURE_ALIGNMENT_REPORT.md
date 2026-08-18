# ARGUS — Architecture Alignment & Implementation Blueprint

**Version:** Architecture v1.0 Draft for Claude Code Alignment  
**Date:** 17 August 2026  
**Purpose:** Establish a single, detailed source of truth for what Argus is, what has already been built, what must change, what should be added, how the system should be organized, and how Claude Code should proceed without inventing a conflicting architecture.

> This document is intentionally more detailed than a normal architecture overview. It is meant to be read by both the founder and Claude Code, and then used to update the repository’s architectural documentation, implementation roadmap, internal engineering graph, and checklists.

---

## 0. Executive decision

Argus should **not** be rebuilt from scratch.

The existing `Argus_OS` codebase has several strong foundations that align with the intended product:

- one reusable contract (`LINK`);
- a modular hardware abstraction layer (`HAL`);
- per-machine manifests;
- a fleet world-model service (`TRACK`);
- a C2 operator application;
- deterministic local task execution;
- offline/disconnected continuation;
- an AI capability gateway;
- early Land/Air/Sea neutrality in the schema.

However, the current code is primarily an **operating-system skeleton and coordination layer**, not yet the autonomous cognitive system we intend Argus to become.

The target is:

> **One modular, edge-native Argus OS that runs on autonomous machines across Land, Air, and Sea. Each machine must be capable of perceiving, understanding, remembering, reasoning, planning, verifying, acting, and safely adapting without relying on cloud or command-link availability. When connectivity exists, machines synchronize into a Maven-like fleet intelligence layer in Argus C2.**

The highest-priority architectural correction is to fix the boundaries around **perception, localization, local persistence, and vehicle control** before adding a large cognitive layer on top.

The highest-priority product addition is the **Argus Cognitive Runtime / Harness**, running locally on each machine.

The highest-priority organizational addition is an **Argus Engineering Knowledge Graph** that describes the codebase itself: components, interfaces, tests, dependencies, status, blockers, decisions, risks, research references, releases, and hardware evidence.

---

# 1. Evidence hierarchy and how Claude should interpret this document

There are four classes of statements in this report.

### A. AS-BUILT FACT

Derived from the code-derived audit `argus-as-built-audit.md` supplied on 17 August 2026.

These describe what is actually implemented as of:

- `Argus_OS` main at commit `3c26521` (2026-08-11);
- audit date 2026-08-17;
- reported tests: 141 passing, 1 failing.

Claude must re-check the current repository before modifying code, because the repository may have changed after that commit.

### B. FOUNDER ARCHITECTURE DECISION

A direction explicitly decided in the architecture discussion.

Claude should treat these as requirements unless implementation reality creates a genuine conflict. If a conflict exists, Claude should document it as an open decision instead of silently choosing another architecture.

### C. RESEARCH-DERIVED RECOMMENDATION

A design recommendation informed by current robotics/embodied-AI/platform research and current vendor capabilities.

These should guide implementation, but Claude may propose a better implementation when it can explain the tradeoff with evidence.

### D. OPEN ARCHITECTURAL DECISION

An area intentionally not frozen.

Claude should investigate the code/hardware/dependencies, propose options, and document the decision. Claude must **not** fill these gaps with an unstated assumption.

---

# 2. What Argus is

## 2.1 Product definition

Argus is an **autonomy operating system and fleet intelligence platform for unmanned machines**.

It should allow different physical machines to share:

- a common language;
- a common ontology;
- a common perception contract;
- a common mission/task model;
- a common local cognitive runtime;
- a common safety philosophy;
- a common communication contract;
- a common fleet-level world model;
- a common C2 experience;
- a common learning and deployment pipeline.

The machine body may be a:

- UGV;
- UAV;
- USV;
- fixed sensor;
- future autonomous platform.

The physical body changes.

The core Argus intelligence architecture should not.

## 2.2 One brain architecture, many bodies

We do **not** want:

- a completely separate Argus Land brain;
- a completely separate Argus Air brain;
- a completely separate Argus Sea brain.

We want:

```text
                         ARGUS CORE
                             |
                    Cognitive Runtime
                             |
                     Shared Ontology
                             |
                     Shared Skill API
                             |
             +---------------+---------------+
             |               |               |
        ARGUS DRIVE      ARGUS FLIGHT     ARGUS SEA
             |               |               |
            UGV             UAV             USV
```

`Drive`, `Flight`, and `Sea` are domain execution layers.

They know how a particular embodiment performs a requested skill.

Example:

```text
Cognitive Runtime requests:
    return_home()

Land implementation:
    path planning -> Nav2 -> steering/throttle/brake

Air implementation:
    3D route -> flight controller -> flight actuators

Sea implementation:
    marine route -> heading/thrust/rudder
```

The cognitive runtime should reason in terms of **goals and capabilities**, not wheel PWM or rotor RPM.

---

# 3. Non-negotiable Argus architecture laws

These should become explicit repository laws and, where possible, automated CI checks.

## LAW 1 — Edge autonomy

The mission path must operate locally on the machine.

No cloud service may be required for:

- perception;
- localization;
- current world state;
- task execution;
- safety;
- navigation;
- contingency behavior;
- return-to-safe-state behavior.

> Connectivity enhances Argus. Connectivity must never create autonomy.

## LAW 2 — One cognitive architecture across domains

Land, Air, and Sea share one Argus cognitive runtime and ontology.

Domain-specific behavior belongs below the skill boundary.

## LAW 3 — Hardware is replaceable

No high-level Argus component should depend directly on:

- ZED-specific classes;
- a specific GNSS;
- a specific IMU;
- a specific motor controller;
- a specific flight controller;
- a specific Jetson model.

Every hardware dependency must cross an explicit adapter/provider boundary.

## LAW 4 — Models are replaceable

Argus must not be “a Nemotron system,” “a Gemma system,” or “a Cosmos system.”

Models are providers behind capability interfaces.

## LAW 5 — No Chinese-origin deployed AI models

This is a **project deployment policy**.

Every deployable model must have an origin, license, checksum, approval state, and deployment profile.

An unapproved model must fail closed.

Do not interpret this document as making a general legal claim about all Indian-government deployments; treat it as an Argus product requirement until the company’s formal compliance policy says otherwise.

## LAW 6 — Models do not directly command actuators

A reasoning/VLM/LLM may propose:

- a plan;
- a typed action;
- a skill invocation;
- parameters within bounded schemas.

It must not directly generate arbitrary motor/relay commands.

Physical actions pass through:

```text
Reasoning
   -> typed plan
   -> action verification
   -> safety governor
   -> skill
   -> domain controller
   -> hardware driver
```

## LAW 7 — No uncontrolled self-modification in the field

During a mission, a machine may:

- update world state;
- update memory;
- replan;
- adapt behavior within approved policy boundaries.

It must not silently retrain foundational weights and deploy the new policy into the same live mission.

Policy/model improvements flow through a controlled learning pipeline:

```text
experience -> training/simulation -> evaluation -> safety regression
-> approval/signing -> deployment
```

## LAW 8 — No snowflake machines

Manual SSH repair is allowed for debugging.

A permanent fix must return to:

```text
Git -> tests -> versioned release -> deployment
```

A field device must not become a unique, undocumented fork.

## LAW 9 — Offline truth is first-class

Every machine must have enough persistent local state to recover identity, mission, home/safe state, configuration, and relevant memory after process restart or device reboot.

## LAW 10 — Provenance is never lost

Argus should be able to answer:

- which sensor produced this observation?
- when?
- on which machine?
- with what confidence?
- which model transformed it?
- which decision used it?
- which action followed?
- which software/model version was running?

## LAW 11 — “Built” has evidence levels

Do not label something simply “done.”

Use explicit maturity states such as:

1. `planned`
2. `scaffolded`
3. `simulated`
4. `software_verified`
5. `hardware_integrated`
6. `field_validated`
7. `deprecated`

## LAW 12 — Architecture must be queryable

The codebase itself must have a machine-readable engineering graph so a human or Claude can answer:

- What exists?
- What is incomplete?
- What depends on this?
- Which tests cover it?
- What hardware has validated it?
- Which ADR explains it?
- Which research inspired it?
- What blocks it?
- What release introduced it?

---

# 4. Current as-built system: preserve vs change

The current audit describes four important planes:

```text
LINK  -> common protobuf contract
TRACK -> fleet world model/server
PILOT -> machine edge runtime
C2    -> operator application
```

There is also:

- `gateway/` for AI capability adapters;
- `voice/`;
- `drive/`;
- a parallel teleop bridge/cockpit stack;
- `sim/`;
- a prototype `drive/brain/`.

## 4.1 Preserve

These are fundamentally good architectural investments and should be evolved rather than replaced.

### LINK

Preserve the idea of a stable, versioned, open contract.

Current ontology objects include:

- Entity
- Observation
- Track
- Asset
- Task
- Zone
- Mission
- Relationship

Current wire messages include:

- HEARTBEAT
- TELEMETRY
- OBSERVATION
- TASK
- TASK_STATUS

**Important:** do not break LINK v1 silently.

If future requirements cannot fit cleanly, preserve v1 compatibility and create an explicit versioned evolution path.

### HAL + manifests

The current HAL is one of the strongest parts of the repository.

Preserve:

- driver protocols;
- per-machine manifests;
- registry;
- driver loader;
- refusal to boot when configured drivers are unavailable.

### TRACK

Preserve TRACK as the **fleet-level world model and coordination service**.

Do not make TRACK the only intelligence that matters.

### C2

Preserve C2 as the operator surface.

Expand it into:

- command;
- fleet awareness;
- Maven-like contextual intelligence;
- diagnostics;
- software/fleet status;
- explainability.

### Disconnection behavior

Preserve and strengthen the existing principle:

- machine continues its task;
- observations queue;
- reconnect merges data;
- cloud loss is irrelevant to the mission path.

## 4.2 Change or refactor soon

### A. Sensor abstraction is too narrow

Current:

```text
SensorDriver.poll() -> list[Detection]
```

This is insufficient for the target architecture.

It prevents clean standardized handling of:

- images;
- depth;
- point clouds;
- IMU;
- GNSS;
- semantic masks;
- occupancy/free space;
- detections;
- tracks;
- sensor calibration;
- timing/synchronization.

This is the **highest architectural refactor priority**.

### B. Localization must become its own provider

Current localization effectively hides behind:

```text
LocomotionDriver.pose()
```

This is the wrong long-term boundary.

Create a first-class `LocalizationProvider` / `PoseProvider`.

### C. Parallel vehicle stacks must converge

The current PILOT path and teleop bridge have separate abstractions and contracts.

Do not allow both to become independent hardware owners.

One real vehicle interface, one safety story, one device ownership story.

### D. Local world state is not persistent enough

The current `WorldSlice` is in-memory and disappears on reboot.

That is incompatible with the intended autonomous edge system.

### E. The current “brain” is a prototype, not the Argus brain

The direct Anthropic `drive/brain/` prototype should not become the production architecture.

Keep useful experiments, but route future AI through capability/model abstractions and the local Cognitive Runtime.

---

# 5. Target system architecture

```text
                                   HUMAN / OPERATOR
                                          |
                                          v
+--------------------------------------------------------------------------------+
|                                  ARGUS C2                                      |
|                                                                                |
| Map | Missions | Fleet Health | Natural Language | Brain State | Diagnostics   |
| Maven-like Fleet Intelligence | Manual/Assisted/Autonomous Control             |
+-----------------------------------------+--------------------------------------+
                                          |
                                      ARGUS LINK
                                          |
                            connection may be absent
                                          |
          +-------------------------------+-------------------------------+
          |                               |                               |
          v                               v                               v
     LAND MACHINE                    AIR MACHINE                      SEA MACHINE
     Jetson Orin/Thor                Jetson/compute                  Jetson/compute
          |                               |                               |
          +-------------------------------+-------------------------------+
                                          |
                            EACH MACHINE RUNS LOCALLY
                                          |
+--------------------------------------------------------------------------------+
|                                  ARGUS OS                                      |
|                                                                                |
|  +--------------------------------------------------------------------------+  |
|  |                      ARGUS COGNITIVE RUNTIME / HARNESS                   |  |
|  |                                                                          |  |
|  |  PERCEIVE -> UNDERSTAND -> REMEMBER -> IMAGINE -> DECIDE                |  |
|  |       -> VERIFY -> ACT -> OBSERVE -> ADAPT                               |  |
|  +----------------------------+---------------------------------------------+  |
|                               |                                                |
|  +----------------------------v---------------------------------------------+  |
|  |                          LOCAL WORLD MODEL                               |  |
|  | Ontology objects | relations | mission | confidence | provenance         |  |
|  | environment | temporal state | local entity identity | history           |  |
|  +----------------------------+---------------------------------------------+  |
|                               |                                                |
|       +-----------------------+-----------------------+                        |
|       |                       |                       |                        |
|       v                       v                       v                        |
|     MEMORY                 REASONING                PLANNER                    |
|       |                       |                       |                        |
|       +-----------------------+-----------------------+                        |
|                               |                                                |
|                         ACTION VERIFIER                                        |
|                               |                                                |
|                         SAFETY GOVERNOR                                        |
|                               |                                                |
|                           SKILL LIBRARY                                        |
+-------------------------------+------------------------------------------------+
                                |
                     DOMAIN EXECUTION LAYER
                                |
              +-----------------+-----------------+
              |                 |                 |
              v                 v                 v
         ARGUS DRIVE       ARGUS FLIGHT       ARGUS SEA
              |                 |                 |
              +-----------------+-----------------+
                                |
                   HARDWARE / DEVICE ABSTRACTION
                                |
       +------------------------+---------------------------+
       |                        |                           |
       v                        v                           v
   PERCEPTION              LOCALIZATION                  CONTROL
   adapters/providers      providers                     drivers
       |                        |                           |
 ZED / thermal /         GNSS / IMU /                  MCU / CAN /
 radar / future          VSLAM / fusion                motors / actuators
```

Surrounding planes:

```text
FLEET PLANE
local world models -> LINK -> TRACK -> Fleet Ontology/World -> C2

LEARNING PLANE
mission experience -> datasets -> Isaac/Simulation -> RL/post-training
-> evaluation -> signed policy/model release -> devices

OPERATIONS PLANE
Git -> CI -> signed release -> private registry -> staged deployment
-> health check -> rollback

ENGINEERING KNOWLEDGE PLANE
code + manifests + tests + ADRs + research + releases
-> Engineering Knowledge Graph
-> generated STATUS / dependency diagrams / impact queries
```

---

# 6. Ontology: the common language of Argus

Ontology should be a **first-class architectural layer**.

A useful Palantir-inspired mental model is:

- **Objects** = nouns
- **Properties** = facts about nouns
- **Links** = relationships
- **Actions** = verbs that can change operational state
- **Functions** = reusable logic over the ontology

This pattern maps well to Argus.

## 6.1 Operational ontology

Examples of object types:

- `Asset`
- `Machine`
- `Sensor`
- `Entity`
- `Person`
- `Vehicle`
- `Obstacle`
- `Route`
- `Waypoint`
- `Zone`
- `Mission`
- `Task`
- `Observation`
- `Track`
- `Capability`
- `SoftwareVersion`
- `ModelVersion`
- `Operator`
- `Event`

Examples of relationships:

```text
Sensor      --mounted_on-->      Asset
Observation --produced_by-->     Sensor
Observation --supports-->        Track
Track       --represents-->      Entity
Asset       --assigned_to-->     Mission
Mission     --contains-->        Task
Route       --intersects-->      Zone
Obstacle    --blocks-->          Route
Asset       --has_capability-->  Navigate
Asset       --located_in-->      Zone
Task        --requires-->        Capability
Decision    --based_on-->        Observation
Action      --executed_by-->     Asset
```

Examples of actions:

- `navigate`
- `patrol`
- `inspect`
- `follow`
- `hold`
- `return_home`
- `dock`
- `land`
- `cancel_task`
- `request_operator_review`

## 6.2 Ontology vs world model

Do not confuse them.

**Ontology:**
what kinds of things and relationships Argus understands.

**World model:**
the current instantiated belief about reality.

Example:

```text
Ontology rule:
    Route can be BLOCKED_BY Obstacle

Current world:
    Route-A BLOCKED_BY Obstacle-229
```

## 6.3 Local and fleet ontology must speak the same language

Each machine maintains local operational truth.

TRACK maintains fleet truth.

They should share compatible semantics, IDs/provenance rules, and action definitions even if their physical storage differs.

## 6.4 Do not require a graph database just because the model is a graph

Start with the simplest reliable persistence.

A logical ontology graph can be represented with:

- protobuf;
- relational tables;
- edge tables;
- indexed SQLite/PostgreSQL;
- in-memory graph projections.

Adopt a dedicated graph database only when query/load requirements justify it.

---

# 7. NEW: Argus Engineering Knowledge Graph

This is separate from the runtime operational ontology.

The operational graph answers:

> What is happening in the physical world?

The engineering graph answers:

> What is happening inside the Argus product and codebase?

Do **not** mix these into one database.

## 7.1 Why build this

The repository is becoming large enough that architecture drift becomes a product risk.

A machine-readable graph should make it possible to query:

- What components are planned?
- Which are implemented only in simulation?
- Which have run on real hardware?
- Which interface does this module implement?
- Who/what consumes it?
- Which tests validate it?
- Which hardware does it run on?
- Which ADR created this decision?
- Which research paper inspired this mechanism?
- What blocks this feature?
- Which open decisions affect it?
- Which release last changed it?
- If I change `LocalizationProvider`, what might break?

## 7.2 Suggested engineering entity types

```text
Component
Module
Service
Interface
Driver
Adapter
Capability
Repository
Directory
Device
HardwareBody
Model
ModelProvider
Dataset
Test
Requirement
ArchitectureLaw
Decision
OpenDecision
Risk
Bug
Task
Milestone
ResearchReference
PatentCandidate
Release
DeploymentProfile
Owner
```

## 7.3 Suggested relationships

```text
IMPLEMENTS
DEPENDS_ON
EXPOSES
CONSUMES
PRODUCES
RUNS_ON
DEPLOYED_TO
TESTED_BY
VALIDATED_ON
BLOCKED_BY
SUPERSEDES
DECIDED_BY
GOVERNED_BY
INSPIRED_BY
ADDRESSES
VIOLATES
OWNS
PART_OF
USES
GENERATES
SYNC_WITH
```

## 7.4 Status taxonomy

Every engineering component gets one maturity state:

```text
planned
scaffolded
simulated
software_verified
hardware_integrated
field_validated
deprecated
```

Additional orthogonal health/status fields:

```text
health: healthy | degraded | failing | unknown

implementation:
  complete: true/false
  blockers: [...]
  known_gaps: [...]

evidence:
  tests: [...]
  hardware_runs: [...]
  logs: [...]
  release: ...
```

## 7.5 Suggested storage

Do not start with Neo4j unless needed.

Start repository-native and reviewable:

```text
architecture/
  graph/
    components.yaml
    relationships.yaml
    requirements.yaml
    risks.yaml
    decisions.yaml
    research.yaml
    releases.yaml
```

Then build a small compiler/indexer that:

1. validates references;
2. checks for orphan components;
3. produces Mermaid diagrams;
4. produces dependency graphs;
5. produces `STATUS.md`;
6. produces “what is incomplete?” reports;
7. exposes a local query API/CLI;
8. eventually feeds an Engineering Console UI.

Possible generated database:

```text
var/engineering_graph.db
```

The YAML/JSON source remains Git-reviewable; the DB is generated.

## 7.6 Proposed developer queries

```bash
argus graph status
argus graph incomplete
argus graph blockers
argus graph component perception.zed
argus graph impact localization.provider
argus graph why cognitive.action_verifier
argus graph research memory
argus graph untested
argus graph hardware-unvalidated
argus graph violated-laws
```

Claude should be encouraged to query this graph before large changes.

## 7.7 Avoid manual duplication

The graph should generate portions of:

- `STATUS.md`;
- dependency diagrams;
- implementation checklist views.

Do not manually maintain five conflicting copies of “what is done.”

---

# 8. Perception architecture

## 8.1 ZED’s role

ZED is the current primary vision sensor.

ZED should be treated as:

> **the eyes and part of the spatial sensing layer, not the Argus brain.**

Use Stereolabs capabilities where they are already strong:

- stereo/depth;
- motion sensing;
- positional tracking where appropriate;
- spatial AI;
- TERRA AI where it provides useful outputs;
- multi-camera fusion where useful.

Do not rebuild low-level stereo vision simply to make it “Argus.”

## 8.2 The correct boundary

```text
Physical world
    |
ZED cameras
    |
ZED SDK / TERRA / Stereolabs capabilities
    |
ZED adapter/provider
    |
ARGUS PERCEPTION INTERFACE
    |
Local World Model
```

Later:

```text
Different camera
    |
Different adapter
    |
SAME ARGUS PERCEPTION INTERFACE
```

## 8.3 Replace the Detection-only boundary

Create a richer set of typed interfaces.

Illustrative design:

```text
FrameStream
DepthStream
PointCloudStream
ImuStream
GnssStream
DetectionStream
TrackStream
SemanticStream
OccupancyStream
CalibrationProvider
SensorHealthProvider
```

Do not require every sensor to provide every stream.

Capabilities should be discoverable.

Example:

```yaml
sensor:
  id: zed-front
  provider: stereolabs_zed
  capabilities:
    - rgb
    - stereo_depth
    - imu
    - detections
    - positional_tracking
```

## 8.4 Keep high-bandwidth local data local by default

Do not put raw full-rate video/depth into LINK just because it exists.

Separate:

- **local sensor bus** for high-rate perception;
- **semantic LINK messages** for fleet communication;
- **recording pipeline** for selected raw experience;
- optional streamed video when explicitly requested.

## 8.5 Immediate ZED blocker from current audit

The audit reports:

- no ZED driver exists in the repo;
- ZED SDK is present on the Jetson;
- currently installed ZED X driver support does not match the flashed L4T kernel;
- no camera was physically attached at audit time;
- licensing/air-gapped behavior was still unverified.

Claude must re-check this on the actual Jetson before assuming the ZED path is ready.

---

# 9. Localization architecture

Localization becomes a first-class subsystem.

```text
GNSS -----+
          |
IMU ------+--> LocalizationProvider --> PoseEstimate
          |
VSLAM ----+
          |
Wheel/vehicle odometry
```

`PoseEstimate` should carry more than latitude/longitude.

Illustrative fields:

```text
timestamp
frame
position
orientation
linear_velocity
angular_velocity
covariance / uncertainty
source_contributions
health
confidence
```

This allows:

- ZED-native localization today;
- cuVSLAM tomorrow;
- fused GNSS/IMU/VSLAM later;
- a different provider on a UAV;
- a marine localization stack on a USV.

The rest of Argus should not care which provider is active.

---

# 10. Local World Model and local persistent storage

Every autonomous machine should have its own local understanding of reality.

## 10.1 Local World Model responsibilities

It should hold:

- self identity;
- current pose and confidence;
- current mission/task;
- home/safe location(s);
- nearby entities/tracks;
- obstacles;
- local zones/routes;
- current plan;
- recent decisions;
- sensor health;
- available capabilities;
- communication state;
- relevant history;
- provenance;
- confidence/uncertainty.

## 10.2 Persistence

Current `WorldSlice` is memory-only.

Target:

### Structured persistent store

For v1, SQLite is appropriate unless profiling proves otherwise.

Suggested database:

```text
var/argus_local.db
```

Possible logical tables:

```text
identity
configuration_snapshots
missions
tasks
task_state_history
entities
relationships
observations_index
local_tracks
world_events
plans
decisions
action_records
memory_items
safe_locations
sync_cursors
software_state
model_state
health_events
```

Use WAL mode where appropriate and design for crash recovery.

### Append-only experience/event journal

Critical decisions and state transitions should be append-only.

This gives us:

- replay;
- debugging;
- causal reconstruction;
- sync;
- learning datasets.

### Heavy sensor recordings

Do not put large video/depth blobs inside the relational DB.

Use:

- ZED SVO where useful;
- ROS 2 bag/MCAP where appropriate;
- file/object segments with indexed metadata.

The DB stores references and metadata.

## 10.3 Reboot behavior

A reboot should not produce amnesia.

On restart:

```text
load machine identity
load signed configuration
load last known safe/home state
load unfinished task
load local world snapshot
replay journal after snapshot
validate sensors/controllers
decide whether task may safely resume
otherwise enter configured contingency state
```

Do not automatically resume physical motion simply because a task was RUNNING before reboot.

---

# 11. Argus Cognitive Runtime / Harness

This is the missing heart of the target architecture.

The harness is **not one LLM**.

It is the runtime that connects:

- perception;
- ontology;
- world state;
- memory;
- models;
- planners;
- tools;
- skills;
- verification;
- safety;
- execution;
- feedback.

## 11.1 Core loop

Target conceptual loop:

> **PERCEIVE → UNDERSTAND → REMEMBER → IMAGINE → DECIDE → VERIFY → ACT → OBSERVE → ADAPT**

“Learn” exists at two timescales:

- in-mission learning via memory/replanning;
- offline/controlled model/policy learning via the Learning Plane.

## 11.2 Recommended internal components

```text
CognitiveRuntime
|
+-- EventBus
+-- WorldModelClient
+-- MemoryManager
+-- Executive
+-- ModelGateway
+-- Planner
+-- ActionVerifier
+-- ContingencyManager
+-- SkillRegistry
+-- SkillExecutor
+-- ExplanationRecorder
```

## 11.3 Avoid a free-chat multi-agent swarm

Do not create dozens of agents that continuously message each other.

Prefer:

- one shared world state;
- bounded specialist capabilities;
- typed tool contracts;
- explicit ownership;
- event-driven invocation.

Example bounded specialists:

```text
MissionPlanner
SceneReasoner
RouteReasoner
DiagnosticsReasoner
MemorySummarizer
OperatorAssistant
```

They are **roles/tools inside the harness**, not independent sovereign brains.

## 11.4 Typed plan output

Models should output a schema, not arbitrary prose for execution.

Illustrative:

```yaml
plan_id: ...
goal: inspect_zone
assumptions:
  - route_b_traversable
steps:
  - skill: navigate
    target: waypoint-27
  - skill: inspect
    target: zone-bravo
constraints:
  max_speed_mps: ...
contingency:
  low_confidence: return_home
confidence: 0.86
```

## 11.5 Action verification

Before a physical skill executes:

```text
Does the proposed action match the stated plan?
Is the skill available?
Are parameters within limits?
Does the ontology permit the action?
Does the mission permit it?
Does current world state invalidate assumptions?
Does the safety governor permit it?
```

If not:

```text
reject -> replan / request review / contingency
```

## 11.6 Confidence and “confused” behavior

The founder requirement is:

> If the machine is uncertain and cannot safely continue, it should return to its safe/home location.

Implement this as a **configurable contingency policy**, not a universal hard-coded action, because Air/Sea/Land failure modes differ.

Example:

```yaml
contingency_policy:
  perception_degraded:
    first: slow
    then: reobserve
    then: return_home
  localization_lost:
    land: hold_then_return_if_recovered
    air: execute_flight_safe_policy
    sea: hold_or_return_if_safe
  mission_ambiguous:
    if_connected: request_operator
    if_disconnected: return_home
```

The high-level principle is common; the safe physical response can be domain-specific.

---

# 12. Memory architecture

Memory is not just “LLM chat history.”

Use multiple memory timescales.

## 12.1 Working / sensory memory

Seconds to minutes.

Examples:

- recent frames/features;
- current object continuity;
- temporary occlusion;
- recent pose trajectory;
- current plan state.

## 12.2 Episodic memory

Mission events.

Examples:

```text
14:33 entered Zone A
14:35 Route A became blocked
14:36 replanned via Route B
14:42 operator override
14:44 mission resumed
```

## 12.3 Semantic memory

Compressed reusable knowledge.

Examples:

```text
Route A is frequently obstructed after rain.
Sensor zed-front experiences glare at this heading.
Dock-2 approach is unreliable from the east.
```

Semantic memory must preserve provenance and confidence.

Do not allow anecdotal one-off events to silently become “truth.”

## 12.4 Fleet memory

When connected, selected machine experiences synchronize to TRACK/fleet storage.

Fleet knowledge may later be redistributed to machines after validation.

---

# 13. “Imagine”: world models and predictive reasoning

The cognitive runtime should eventually be capable of evaluating possible futures.

This does not mean every decision requires a giant generative world model.

Create a capability abstraction:

```text
FuturePredictor / WorldModelProvider
```

Possible providers may include:

- deterministic simulation;
- kinematic prediction;
- learned world model;
- NVIDIA Cosmos family;
- domain-specific predictors.

Example:

```text
Current world:
  Route A contains moving obstacle

Candidate plan A:
  continue

Candidate plan B:
  slow and wait

Candidate plan C:
  use Route B

Future predictor estimates consequences
Planner compares outcomes
Verifier checks selected action
```

Treat predictive models as advisory unless their outputs meet validated reliability requirements.

---

# 14. Skills and domain execution

## 14.1 Universal skill contract

The cognitive runtime should request capabilities through typed skills.

Potential common skills:

```text
navigate
patrol
hold
inspect
follow
return_home
dock
report
observe
relocalize
```

Not all domains implement all skills.

## 14.2 Argus Drive

Argus Drive remains important.

Definition:

> **Argus Drive is the Land-domain execution layer that translates Argus skills into UGV navigation and vehicle control.**

It owns Land-specific concerns such as:

- ground navigation;
- terrain constraints;
- steering;
- throttle;
- braking;
- Land-domain safe stop;
- ground-specific controllers;
- drive-by-wire integration.

It should **not** own the universal brain.

## 14.3 Argus Flight

Future Air-domain implementation.

Owns:

- flight controller integration;
- 3D navigation;
- altitude;
- flight-domain failsafes;
- takeoff/landing/docking;
- air vehicle state.

## 14.4 Argus Sea

Future marine implementation.

Owns:

- marine navigation;
- heading;
- thrust/rudder;
- water-domain constraints;
- docking;
- sea-state/environment inputs where relevant.

---

# 15. Safety architecture

Safety must sit below model reasoning.

## 15.1 Safety hierarchy

```text
Human emergency controls
        |
Safety MCU / low-level watchdog
        |
Domain safety controller
        |
Argus Safety Governor
        |
Skill Executor
        |
Reasoning / Planner
```

Higher intelligence cannot bypass a lower safety layer.

## 15.2 Immediate physical UGV safety gate

The current audit reports critical real-vehicle issues at audit time:

- deployed MCU firmware can hold last throttle on link loss;
- steering feedback was disconnected;
- brake relays were disconnected;
- e-stop/ignition control was incomplete;
- replacement watchdog firmware was written but not yet bench-verified/flashed.

**Do not run autonomous moving-hardware tests until the current state is re-verified and the low-level fail-safe path is proven.**

This is a hard implementation gate, not a documentation preference.

## 15.3 Safety behavior must be deterministic

LLMs can suggest.

The safety layer decides whether execution is permitted.

---

# 16. TRACK: fleet world model

TRACK should remain the fleet truth service.

Expand it carefully.

## 16.1 TRACK responsibilities

- ingest semantic observations;
- fuse/reconcile entity identity;
- maintain fleet assets;
- missions/tasks;
- zones;
- relationships;
- event history;
- fleet memory;
- autonomy modes;
- machine health;
- software/model versions;
- sync state.

## 16.2 Local vs fleet truth

Do not require a machine to call TRACK for every decision.

```text
Machine local world model:
    authoritative for immediate local execution

TRACK:
    authoritative for fleet-level coordinated view
```

Synchronization must preserve:

- origin;
- timestamps;
- confidence;
- provisional identity;
- conflict resolution history.

---

# 17. Argus C2 + Maven-like Fleet Intelligence

Argus C2 should evolve beyond “map with buttons.”

It should become the human-facing fleet intelligence layer.

## 17.1 C2 responsibilities

### Operational picture

- machines;
- tracks;
- observations;
- zones;
- missions;
- routes;
- alerts.

### Machine health

- battery;
- compute utilization;
- Jetson temperature;
- storage;
- ZED/sensor health;
- localization status;
- controller health;
- communications;
- software/model versions.

### Brain state

The operator should be able to understand:

- current mission;
- current plan;
- current autonomy mode;
- why a plan changed;
- confidence;
- uncertainty;
- contingency state;
- last major decision.

### Goal-based control

Primary normal interaction should be goals such as:

```text
Go to Point B.
Patrol this perimeter.
Inspect Zone C.
Return home.
```

Manual teleop remains a fallback/maintenance/emergency capability.

## 17.2 Maven-like intelligence layer

Inspired by the general Maven Smart System pattern:

```text
many sensors/assets/data
        |
fleet world model / ontology
        |
AI reasoning and contextual analysis
        |
human operational workflow
        |
bounded tasking/actions
```

Argus should allow an operator to ask contextual questions and issue high-level intent.

Illustrative:

```text
"Which machine is closest to Zone Bravo and healthy enough to inspect it?"

"Show me all assets whose front perception is degraded."

"Send the nearest eligible land machine to inspect this location."
```

The model does not get to invent machine IDs or bypass permission checks.

Natural-language references resolve against the ontology.

Actions become typed tasks through the normal task API.

## 17.3 Critical Argus difference

C2 may be unavailable.

Each machine still has its own brain.

> Connected: Argus has fleet intelligence.  
> Disconnected: each machine remains autonomous.

---

# 18. Communications and LINK

LINK remains the common semantic contract.

Do not tie higher layers to a single transport.

Current MQTT can remain one provider.

Future transports may include:

- Ethernet;
- Wi-Fi;
- private RF;
- mesh;
- satellite;
- tactical/field networks.

Transport capability belongs behind a communications interface.

The cognitive runtime should react to **communication state**, not a particular radio implementation.

No asset-to-asset mesh exists in the current audit. Design for it as a future possibility, but do not block v1 on it.

---

# 19. Local model architecture

## 19.1 Do not choose one permanent “base LLM”

Create a capability-based Model Gateway.

Example:

```text
ModelGateway
|
+-- physical_scene_reasoning
+-- mission_reasoning
+-- tool_calling
+-- operator_qa
+-- memory_summarization
+-- embedding
+-- future_prediction
```

Each capability maps to an approved provider.

## 19.2 Candidate families to benchmark

As of August 2026, reasonable non-Chinese-origin candidates include:

### NVIDIA Cosmos

Use for physical-world reasoning/prediction experiments.

Cosmos 3 and related models are directly relevant to:

- physical reasoning;
- world prediction;
- physical AI;
- world/action modeling.

NVIDIA’s current ecosystem is especially attractive because Argus already targets Jetson and Isaac.

### NVIDIA Nemotron

Use as a candidate for:

- agentic reasoning;
- structured tool use;
- mission reasoning;
- local orchestration.

Do not assume a particular Nemotron configuration fits Orin latency/memory requirements until benchmarked on the actual device.

### Google Gemma 4

Benchmark edge-appropriate variants for:

- reasoning;
- multimodal understanding;
- structured output;
- tool workflows.

### Microsoft Phi-4 Mini

Useful candidate for small/fast utility functions such as:

- routing;
- classification;
- lightweight tool use;
- compact reasoning.

## 19.3 Model benchmark before freeze

Create a real Argus model evaluation harness.

Evaluate on the actual Jetson Orin 64GB.

Metrics:

```text
cold start
tokens/sec
first-token latency
end-to-end decision latency
VRAM/RAM
power draw
thermal behavior
structured-output validity
tool-call accuracy
mission planning accuracy
scene reasoning accuracy
hallucination rate
recovery from ambiguous instruction
long-session stability
offline startup
license/origin compliance
```

Use Argus-specific tasks, not generic leaderboard scores.

## 19.4 Model registry

Every deployed model:

```yaml
id:
provider:
family:
version:
origin_country:
license:
weights_hash:
quantization:
capabilities:
approved_profiles:
benchmark_id:
approved_by:
```

A model that fails policy must not load.

---

# 20. ZED + NVIDIA division of responsibility

Recommended principle:

> **Let Stereolabs solve excellent sensing. Let NVIDIA provide strong physical-AI infrastructure. Let Argus own the architecture that turns sensing into autonomous behavior.**

Argus proprietary value should concentrate on:

- ontology;
- local/fleet world-model relationship;
- memory;
- cognitive harness;
- model routing;
- skills;
- action verification;
- contingency reasoning;
- synchronization;
- fleet intelligence;
- experience/learning pipeline;
- embodiment abstraction.

---

# 21. Experience collection and learning plane

The current audit reports no real RL/training/data pipeline.

Build the data flywheel deliberately.

## 21.1 Record meaningful missions

Experience record should link:

```text
mission
task
sensor streams
world-state changes
observations
plans
model calls
decisions
action verification
skill invocations
operator interventions
vehicle telemetry
outcome
software version
model version
```

## 21.2 Storage formats

Use structured metadata in DB/event journal.

Use MCAP/rosbag/SVO/files for heavy streams.

Everything must share synchronized timestamps and mission IDs.

## 21.3 Three learning speeds

### Fast loop: milliseconds/seconds

```text
perceive -> update world -> plan -> act -> correct
```

No weight changes.

### Experience loop: minutes/hours

```text
record -> summarize -> update episodic/local semantic memory
```

### Training loop: offline/controlled

```text
dataset
-> simulation/world model
-> imitation/RL/post-training
-> evaluation
-> regression
-> approval
-> signed release
```

---

# 22. Simulation and reinforcement learning

Use modern simulation/learning infrastructure rather than inventing a physics stack.

Preferred research/development path:

- NVIDIA Isaac Sim for physical simulation/testing/synthetic data;
- NVIDIA Isaac Lab for RL/imitation/policy training;
- domain randomization;
- sim-to-real evaluation;
- world-model-based RL experiments where justified.

The Jetson primarily runs **inference/deployed policies**.

Large-scale training should not be architecturally dependent on training directly on the field Jetson.

---

# 23. Research mapped to architecture decisions

Research should not be included as decoration.

For each work, record:

1. what problem it solves;
2. what we take from it;
3. what we do **not** assume;
4. which Argus component it influences.

## R1 — Vesta: A Generalist Embodied Reasoning Model (NVIDIA, 2026)

**Relevant lesson:**

- generalist embodied reasoning can consolidate localization/navigation/reasoning/planning tasks;
- memory-harness design is valuable for long-horizon embodied behavior.

**Argus implication:**

- build a shared cognitive runtime instead of a swarm of isolated agents;
- memory is a first-class component;
- models remain behind Argus interfaces.

Source:
https://research.nvidia.com/labs/gear/vesta/

## R2 — MEM: Multi-Scale Embodied Memory for Vision Language Action Models (2026)

**Relevant lesson:**

- short-horizon visual memory and compressed long-horizon semantic/text memory serve different purposes.

**Argus implication:**

- working/sensory, episodic, and semantic memory should not be collapsed into one prompt/history buffer.

Source:
https://arxiv.org/abs/2603.03596

## R3 — Do What You Say: Runtime Reasoning-Action Alignment Verification (ICRA 2026)

**Relevant lesson:**

- correct textual reasoning does not guarantee the generated physical action matches the reasoning.

**Argus implication:**

- an explicit `ActionVerifier` belongs between planning/reasoning and skill execution.

Source:
https://research.nvidia.com/publication/2026-06_do-what-you-say-steering-vision-language-action-models-runtime-reasoning-action

## R4 — RISE: Self-Improving Robot Policy with Compositional World Model (2026)

**Relevant lesson:**

- world-model imagination can support policy improvement while reducing costly physical interactions.

**Argus implication:**

- prefer controlled model-based/offline learning over naive live self-training;
- build experience collection early.

Source:
https://arxiv.org/abs/2602.11075

## R5 — VLA-MBPO: Practical World Model-based RL for Vision-Language-Action Models (2026)

**Relevant lesson:**

- model-based rollouts need multi-view consistency and mechanisms to control compounding model error.

**Argus implication:**

- multi-camera experiences should be represented as one physical world;
- world-model outputs need confidence/evaluation;
- keep imagined horizons bounded unless validated.

Source:
https://arxiv.org/abs/2603.20607

## R6 — World-Task Factorization for Robot Learning (2026)

**Relevant lesson:**

- separating world structure from task-specific logic improves generalization across heterogeneous robots/tasks.

**Argus implication:**

This strongly supports:

```text
shared world/ontology
       +
task/skill/domain modules
```

rather than separate full brains for Land/Air/Sea.

Source:
https://arxiv.org/abs/2606.02027

## R7 — NVIDIA Isaac Lab / Isaac Sim

**Relevant lesson:**

- use GPU-accelerated simulation and existing RL/imitation tooling;
- train/test policies in simulation and deploy validated outputs.

Argus implication:

- do not build a custom RL infrastructure before evaluating Isaac Lab.

Sources:
https://developer.nvidia.com/isaac/lab
https://developer.nvidia.com/isaac/sim

## R8 — NVIDIA Cosmos

**Relevant lesson:**

- current physical-AI foundation-model direction combines physical reasoning, prediction/world modeling, and action-oriented modeling.

**Argus implication:**

- Cosmos is a strong provider candidate for “imagine/physical reason” capabilities;
- do not hardwire the architecture to Cosmos.

Source:
https://www.nvidia.com/en-us/ai/cosmos/

## R9 — Stereolabs TERRA AI / ZED SDK

**Relevant lesson:**

- use existing vision/depth/spatial-AI capabilities instead of rebuilding low-level perception.

Argus implication:

- ZED provider under the Argus Perception Interface;
- sensor remains swappable.

Sources:
https://www.stereolabs.com/blog/introducing-zed-sdk-50
https://www.stereolabs.com/our-technology

## R10 — Palantir Ontology

**Relevant lesson:**

Operational systems become easier to reason about when data is expressed as:

- objects;
- properties;
- links;
- actions;
- functions.

Argus implication:

- ontology is not only storage schema; it is the shared operational language linking perception, reasoning, C2, and actions.

Source:
https://palantir.com/docs/foundry/ontology/overview/

## R11 — Maven Smart System / Palantir defense pattern

**Relevant lesson:**

- aggregate heterogeneous operational data into a common picture;
- add contextual AI reasoning;
- integrate results into human operational workflows/tasking.

Argus implication:

- Maven-like fleet intelligence belongs in C2/TRACK;
- it must not replace machine-local autonomy.

Sources:
https://www.palantir.com/offerings/defense/air-space/
https://blog.palantir.com/maven-smart-system-innovating-for-the-alliance-5ebc31709eea

---

# 24. Observability and explainability

Argus must be debuggable.

## 24.1 Every important decision should have an explanation record

Not hidden model chain-of-thought.

Record an operational rationale such as:

```yaml
decision:
  id: ...
  mission: ...
  trigger: route_blocked
  inputs:
    - observation: obs-...
    - localization: pose-...
  selected_plan: plan-b
  reason_codes:
    - primary_route_blocked
    - alternate_route_available
    - alternate_within_mission_constraints
  confidence: 0.91
  verifier: passed
  safety: passed
  software_version: ...
  model_version: ...
```

## 24.2 C2 should expose useful explanations

Example:

```text
TESSY-01
Mission: Deliver to Bravo
State: Navigating
Plan: Route B
Why: Route A blocked by tracked obstacle
Confidence: 91%
Communications: Disconnected
Local autonomy: Active
```

## 24.3 Logs are part of product architecture

Standardize:

- structured logs;
- correlation IDs;
- mission IDs;
- asset IDs;
- trace IDs;
- model-call IDs;
- decision IDs;
- skill execution IDs.

The current audit notes zero logging in the teleop bridge; fix this before it becomes a production path.

---

# 25. Local backup, fleet synchronization, and recovery

Yes: every device should keep local data **and** synchronize important data whenever an approved connection exists.

Call this **Argus Sync**, not merely “cloud backup.”

## 25.1 Local-first rule

A machine reads/writes its local store.

Network is not required.

## 25.2 Incremental sync

Do not repeatedly upload the whole SQLite file.

Use event/delta synchronization:

```text
local append-only events
        |
sync cursor
        |
send unseen events
        |
fleet ingest
        |
ack cursor
```

## 25.3 What to sync

High priority:

- machine identity/config history;
- mission history;
- events;
- observations/track summaries;
- decisions;
- operator interventions;
- health/maintenance history;
- software/model versions;
- experience metadata.

Conditional:

- selected camera clips;
- failures;
- anomalous sensor sequences;
- training samples;
- mission recordings.

## 25.4 Fleet storage need not be public cloud

Possible destinations:

- local ground station;
- on-prem Argus server;
- military/private datacenter;
- private cloud;
- field server.

“Cloud” is a deployment option, not a dependency.

## 25.5 Destruction model

If a machine is destroyed while disconnected, unsynchronized new data is lost.

Synced data survives and can support:

- fleet history;
- maintenance;
- training;
- replacement-machine configuration;
- incident analysis.

---

# 26. Software distribution and fleet deployment

## 26.1 Do not use `git pull` as the production deployment model

Git is the source of development truth.

Production machines receive **versioned releases**.

## 26.2 Development stage: SSH + Ansible

For the first machines:

```text
Git / build machine
      |
Ansible
      |
SSH
      |
Jetson fleet
```

Benefits:

- simple;
- repeatable;
- easy to inspect;
- no custom fleet platform required yet.

## 26.3 Claude Code on prototype Jetsons

Claude Code can be useful in development/maintenance mode for:

- log analysis;
- dependency diagnosis;
- device debugging;
- local code inspection.

But:

> Claude Code must not become a runtime dependency.

Any permanent fix returns to Git.

For hardened deployed profiles, consider disabling/removing development tooling by default.

## 26.4 Later: Argus Fleet Deployment

Concept:

```text
Developer / Claude
       |
      Git
       |
 CI + tests
       |
 signed release
       |
 private Argus registry
       |
 staged deployment
       |
 device health check
       |
 success OR rollback
```

## 26.5 Separate system updates from Argus application updates

### Base system

- JetPack;
- Ubuntu;
- CUDA;
- kernel/BSP;
- low-level drivers.

Use NVIDIA-supported image/OTA mechanisms where possible.

### Argus application

- Argus OS components;
- Cognitive Runtime;
- Drive/Flight/Sea;
- perception adapters;
- models;
- skills;
- configs.

Use versioned packages/containers/artifacts.

## 26.6 Device lifecycle

At factory/provisioning:

```text
flash approved base image
-> enroll device identity
-> provision certificates/keys
-> apply body manifest
-> install approved Argus release
-> run hardware self-test
-> register with fleet
```

At runtime:

```text
check approved release
-> download
-> verify signature
-> install inactive version
-> health check
-> activate
-> rollback on failure
```

## 26.7 SSH remains

Retain three paths:

1. normal: Fleet Deployment;
2. maintenance: authenticated SSH;
3. recovery: physical console/recovery flash.

---

# 27. Security architecture

This report does not attempt to fully specify defense-grade security, but the boundaries must exist now.

Required architecture areas:

- device identity;
- operator identity;
- signed software;
- signed model artifacts;
- encrypted communications;
- secrets management;
- secure boot;
- least privilege;
- audit logs;
- deployment profiles;
- compromised-device revocation;
- break-glass maintenance procedure.

The current audit identifies teleop authentication/logging as substantially weaker than TRACK/C2 security. Treat this as a priority when unifying teleop.

---

# 28. Repository architecture

Recommendation: **do not split everything into many Git repositories yet.**

The current monorepo gives Claude and human engineers one place to understand the system.

Use strong internal boundaries first.

A target structure could evolve toward:

```text
Argus_OS/
|
+-- CLAUDE.md
+-- PROJECT.md
+-- ARCHITECTURE.md
+-- STATUS.md
+-- NEXT-STEPS.md
+-- RESEARCH.md
+-- MODELS.md
+-- DEPLOYMENT.md
+-- SECURITY.md
+-- TESTING.md
|
+-- architecture/
|   +-- ontology/
|   |   +-- operational/
|   |   +-- engineering/
|   +-- graph/
|   +-- decisions/
|   +-- diagrams/
|
+-- core/
|   +-- cognitive_runtime/
|   +-- world_model/
|   +-- memory/
|   +-- reasoning/
|   +-- planning/
|   +-- verification/
|   +-- safety/
|   +-- skills/
|   +-- perception/
|   +-- localization/
|   +-- models/
|
+-- domains/
|   +-- drive/
|   +-- flight/
|   +-- sea/
|
+-- platform/
|   +-- link/
|   +-- track/
|   +-- c2/
|   +-- gateway/
|   +-- voice/
|   +-- sync/
|   +-- deployment/
|
+-- hardware/
|   +-- perception/
|   |   +-- zed/
|   |   +-- thermal/
|   |   +-- radar/
|   +-- localization/
|   +-- controllers/
|
+-- learning/
|   +-- experience/
|   +-- datasets/
|   +-- simulation/
|   +-- rl/
|   +-- evaluation/
|
+-- bodies/
+-- firmware/
+-- sim/
+-- tests/
+-- scripts/
```

**Do not perform this rename/reorganization blindly.**

Claude should first map every existing module to the target architecture, then propose a low-risk migration.

Large moves can destroy history and create unnecessary conflicts.

## 28.1 When to split repositories later

A separate repo is justified when a component has materially independent:

- security boundary;
- release cadence;
- external SDK audience;
- team ownership;
- licensing;
- firmware lifecycle.

Potential future candidates:

- public `argus-link-sdk`;
- hardware firmware;
- separate C2 product;
- model/learning infrastructure.

Not now by default.

---

# 29. Documentation architecture

The repository currently has multiple `.md` files that can drift.

We need one hierarchy of truth.

## 29.1 Root `CLAUDE.md`

Purpose:

- mandatory rules for Claude Code;
- source-of-truth pointers;
- forbidden architectural shortcuts;
- how to update the Engineering Graph;
- how to classify implementation status;
- how to handle open decisions.

Keep it concise enough that Claude actually follows it.

Do **not** duplicate the full architecture inside it.

It should say:

```text
Read ARCHITECTURE.md before architectural changes.
Read STATUS.md / Engineering Graph before claiming something exists.
Read relevant ADR before changing a frozen boundary.
Never mark hardware work complete without hardware evidence.
Never introduce a model/provider outside the Model Gateway.
Never introduce direct hardware dependencies above adapters.
```

## 29.2 `ARCHITECTURE.md`

This report should become the basis for the canonical architecture.

It should contain the target architecture and laws.

## 29.3 `PROJECT.md`

Contains:

- what Argus is;
- target users/use cases;
- major product components;
- current program phase;
- glossary.

## 29.4 `STATUS.md`

Should ideally be generated or partially generated from the Engineering Graph.

Must distinguish:

- simulated;
- software verified;
- hardware integrated;
- field validated.

## 29.5 `NEXT-STEPS.md`

A prioritized executable roadmap.

No aspirational essay.

## 29.6 `MEMORY.md`

If retained:

- durable architectural decisions;
- lessons learned;
- important founder constraints;
- pointers to ADRs.

Do not turn it into a second architecture document.

## 29.7 `AGENTS.md`

Clarify which meaning is intended.

Recommended use:

- rules for software/code agents that work on the repo;
- Cognitive Runtime agent/tool definitions should live under architecture/core docs, not be conflated with Claude’s coding-agent instructions.

If the existing repo already uses this name differently, document that and choose a clearer alternative.

## 29.8 ADRs

Use architecture decision records:

```text
architecture/decisions/
  ADR-0001-edge-first.md
  ADR-0002-one-core-multi-domain.md
  ADR-0003-perception-stream-interface.md
  ADR-0004-localization-provider.md
  ADR-0005-local-world-persistence.md
  ADR-0006-model-gateway.md
  ADR-0007-action-verification.md
  ...
```

Every ADR should contain:

- context;
- decision;
- alternatives;
- consequences;
- status;
- date;
- affected components.

---

# 30. Proprietary IP / patent candidate areas

This section is **not a patentability opinion**.

Do not publicly claim these are patented or patentable without a professional prior-art search and counsel.

The strongest IP is unlikely to be:

- “using an ontology”;
- “using an LLM on a robot”;
- “an autonomous vehicle”;
- “multi-agent harness.”

Those have extensive prior art.

Potentially more defensible inventions may emerge from **specific technical mechanisms**.

## Candidate 1 — Local/fleet world reconciliation under disconnection

Specific mechanisms for:

- provisional identity;
- entity reconciliation;
- confidence/provenance;
- conflicting observations;
- long disconnection;
- eventual synchronization across heterogeneous machines.

## Candidate 2 — Cross-embodiment ontology-driven autonomy

A specific method where:

- universal ontology/mission semantics;
- one cognitive runtime;
- typed capabilities;
- domain execution adapters;

allow one mission/action language to operate across UGV/UAV/USV embodiments.

## Candidate 3 — Confidence-driven autonomous contingency manager

A specific technical mechanism combining:

- mission state;
- perception confidence;
- localization uncertainty;
- environment state;
- connectivity;
- available skills;

to determine:

- continue;
- re-observe;
- replan;
- hold;
- return;
- request operator.

## Candidate 4 — Reasoning/action alignment verification for heterogeneous autonomous platforms

The general concept has prior art, including the 2026 paper referenced above.

A patent candidate would require a genuinely novel Argus-specific technical mechanism beyond the general idea.

## Candidate 5 — Sensor-independent entity provenance/fusion

Specific mechanism that normalizes heterogeneous sensors into an ontology while preserving:

- calibration;
- provenance;
- uncertainty;
- cross-machine identity;
- re-identification;
- sensor replacement.

## Candidate 6 — Controlled experience-to-policy pipeline

A specific mechanism for:

- identifying operational failure events;
- extracting synchronized multimodal experience;
- generating simulated/world-model variants;
- evaluating policies;
- signed promotion to a deployable fleet version.

## Candidate 7 — Engineering/runtime dual ontology tooling

Potentially interesting if Argus develops a novel mechanism connecting:

- operational system graph;
- engineering component graph;
- deployment evidence;
- runtime failures;

to automatically diagnose or safely recommend updates.

### IP process recommendation

For each candidate:

```text
invention note
-> technical problem
-> exact mechanism
-> prior art search
-> inventors
-> diagrams
-> prototype/evidence
-> counsel review
-> file before broad disclosure where appropriate
```

---

# 31. What NOT to build

Claude should avoid these traps.

## Do not build a giant monolithic “AI brain”

No single model should own:

- perception;
- world truth;
- safety;
- motor control;
- mission state;
- memory.

## Do not build three independent operating systems

Drive/Flight/Sea are domains, not separate universes.

## Do not replace strong vendor capabilities without a reason

Do not rewrite:

- stereo depth;
- basic ZED functions;
- physics simulation;
- generic RL infrastructure;
- secure Jetson base-update mechanisms;

unless measurements prove a specific need.

## Do not put raw sensor streams into the fleet ontology by default

Keep high-rate processing local.

## Do not make C2 necessary for local execution

C2 is command/awareness/fleet intelligence.

## Do not let Claude make permanent device-only fixes

Fix -> Git -> release.

## Do not introduce new architecture files that duplicate existing truth

Update/reconcile existing docs.

---

# 32. Migration plan from current codebase

This is an architecture migration, not a greenfield rewrite.

## PHASE 0 — Re-audit and safety gate

- [ ] Re-run full tests.
- [ ] Record current commit.
- [ ] Compare current code to the 17 Aug audit.
- [ ] Resolve/fix the existing bridge race test or document why test logic is wrong.
- [ ] Re-verify physical UGV relay map.
- [ ] Re-verify MCU watchdog state.
- [ ] Bench-verify safety firmware.
- [ ] Verify steering feedback/brake/e-stop current state.
- [ ] Do not begin autonomous moving tests until low-level safety gate passes.
- [ ] Verify actual ZED hardware attached.
- [ ] Verify current JetPack/L4T/ZED SDK/driver compatibility.

**Exit condition:** current truth is known and real hardware can be safely exercised.

## PHASE 1 — Establish architecture source of truth

- [ ] Add/update root `ARCHITECTURE.md`.
- [ ] Update `CLAUDE.md`.
- [ ] Update `PROJECT.md`.
- [ ] Reconcile `ARGUS-OS-PLAN.md` with target architecture.
- [ ] Create ADR structure.
- [ ] Create Engineering Knowledge Graph schema.
- [ ] Populate graph with all existing modules.
- [ ] Add CI graph validation.
- [ ] Generate an accurate `STATUS.md`.
- [ ] Convert current roadmap into status-aware tasks.

**Exit condition:** Claude and humans can query what exists, what is simulated, and what is blocked.

## PHASE 2 — Fix architectural seams

- [ ] Introduce richer Perception interfaces.
- [ ] Preserve old `SensorDriver.poll()` behind compatibility shim while migrating.
- [ ] Introduce first-class LocalizationProvider.
- [ ] Remove localization ownership from locomotion over time.
- [ ] Define Control/Locomotion responsibilities.
- [ ] Reconcile teleop adapter with the HAL.
- [ ] Ensure only one process owns physical control devices.
- [ ] Standardize structured logs/tracing.
- [ ] Define local persistence API.

**Exit condition:** hardware/model replacements do not leak into higher-level code.

## PHASE 3 — Real edge platform proof

- [ ] Run PILOT/Argus edge runtime on the Jetson, not only Mac/CI.
- [ ] Build real UGV locomotion adapter.
- [ ] Integrate ZED provider.
- [ ] Integrate real localization provider.
- [ ] Feed obstacle/perception data into navigation.
- [ ] Validate disconnection on actual Jetson.
- [ ] Record mission experience.
- [ ] Persist/recover local state across reboot.

**Exit condition:** one real UGV can execute a safe, bounded autonomous mission locally.

## PHASE 4 — Cognitive Runtime v1

Start **deterministic-first**.

- [ ] Create `CognitiveRuntime` service/module.
- [ ] Create event bus.
- [ ] Connect Local World Model.
- [ ] Create persistent memory manager.
- [ ] Create typed plan schema.
- [ ] Create Skill Registry.
- [ ] Create ActionVerifier.
- [ ] Create ContingencyManager.
- [ ] Integrate Model Gateway.
- [ ] Add one local reasoning model.
- [ ] Model proposes bounded plans only.
- [ ] Record rationale/reason codes.
- [ ] Test with model unavailable.
- [ ] Ensure system degrades to deterministic behavior.

**Exit condition:** cognitive assistance improves decisions but is not a single point of mission failure.

## PHASE 5 — Model evaluation and physical reasoning

- [ ] Build Argus model benchmark suite.
- [ ] Benchmark NVIDIA physical-reasoning candidate(s).
- [ ] Benchmark Nemotron candidate(s).
- [ ] Benchmark Gemma 4 candidate(s).
- [ ] Benchmark small Phi utility candidate.
- [ ] Record origin/license/hash.
- [ ] Benchmark actual Orin 64GB thermal/power/latency.
- [ ] Select capability-by-capability defaults.
- [ ] Do not select one universal model just for simplicity.

## PHASE 6 — Memory + predictive world-model experiments

- [ ] Implement working/sensory memory.
- [ ] Implement episodic mission memory.
- [ ] Implement semantic memory with provenance.
- [ ] Add memory compaction/summarization.
- [ ] Add FuturePredictor interface.
- [ ] Prototype deterministic prediction.
- [ ] Prototype learned/Cosmos provider where useful.
- [ ] Add confidence gating.
- [ ] Never let unvalidated generated futures directly authorize unsafe actions.

## PHASE 7 — Maven-like C2

- [ ] Add fleet contextual query.
- [ ] Add ontology-backed natural-language interface.
- [ ] Resolve names/entities against TRACK.
- [ ] Add typed task generation.
- [ ] Add operator confirmation policies where required.
- [ ] Add Brain State UI.
- [ ] Add machine diagnostics UI.
- [ ] Add software/model version UI.
- [ ] Add “why?” / decision explanation UI.
- [ ] Add fleet capability search.

## PHASE 8 — Argus Sync

- [ ] Make local event journal syncable.
- [ ] Implement cursor-based incremental sync.
- [ ] Preserve timestamps/provenance.
- [ ] Add retry/idempotency.
- [ ] Add selected media/experience upload policy.
- [ ] Add fleet recovery view.
- [ ] Test weeks-long disconnection in simulation.
- [ ] Test merge after conflicting/provisional identities.

## PHASE 9 — Learning plane

- [ ] Add MCAP/SVO/experience indexing.
- [ ] Build dataset extraction.
- [ ] Integrate Isaac Sim.
- [ ] Integrate Isaac Lab.
- [ ] Create sim-to-real evaluation.
- [ ] Add imitation/RL experiments.
- [ ] Add model-based RL research prototype.
- [ ] Create policy evaluation gates.
- [ ] Sign approved policies.
- [ ] Record lineage from experience -> model -> release.

## PHASE 10 — Fleet deployment

### Immediate
- [ ] Create Ansible inventory.
- [ ] Create idempotent Jetson provisioning playbook.
- [ ] Create versioned Argus install.
- [ ] Add health check.
- [ ] Add rollback procedure.

### Later
- [ ] Private artifact/container registry.
- [ ] Signed releases.
- [ ] Per-device release channel.
- [ ] Staged rollout.
- [ ] Automated rollback.
- [ ] Fleet software UI.
- [ ] Base Jetson OTA separated from Argus application OTA.

## PHASE 11 — Air / Sea expansion

Do this **after** the universal boundaries have survived real Land hardware.

- [ ] Define Air capability manifest.
- [ ] Implement Flight domain.
- [ ] Extend vertical zone semantics.
- [ ] Fix 3D fusion distance.
- [ ] Implement altitude-aware planning.
- [ ] Define Sea capability manifest.
- [ ] Implement Sea domain.
- [ ] Prove Cognitive Runtime does not branch on domain type except through capabilities.

---

# 33. Acceptance tests for the architecture itself

These are not feature tests; they test whether the architecture is real.

## Replace camera test

Swap ZED provider for a simulated/alternate provider.

Expected:

- Cognitive Runtime unchanged.
- World Model unchanged.
- Planner unchanged.
- C2 unchanged.

## Replace reasoning model test

Swap model provider.

Expected:

- no planner/safety/skill code changes;
- only model config/adapter changes.

## Disconnect test

Cut communication during mission.

Expected:

- current safe mission continues if policy permits;
- local world model continues;
- events queue;
- C2 marks machine disconnected;
- reconnect merges.

## Reboot test

Restart edge runtime mid-mission.

Expected:

- identity/config/home recover;
- world state recovers;
- unfinished task is evaluated;
- no blind automatic motion;
- safe resume or contingency.

## Domain test

Run the same logical skill request against Land and simulated Air.

Expected:

```text
skill request is common
execution provider differs
```

## No-model test

Kill local LLM/VLM.

Expected:

- safety/navigation/basic deterministic autonomy still works;
- system reports degraded cognition, not total mission failure.

## Bad-model-action test

Model proposes unavailable/unsafe action.

Expected:

- ActionVerifier rejects;
- no hardware action occurs.

## Engineering graph consistency test

Delete/rename a declared component.

Expected:

- CI detects dangling graph edge or missing implementation metadata.

## “Done” evidence test

A component may not be `hardware_integrated` without linked hardware-run evidence.

---

# 34. Open-ended questions Claude should investigate, not guess

Claude should answer these after inspecting the latest repository and actual Jetson.

## Hardware / perception

1. What exact ZED model(s) are physically available today?
2. What JetPack/L4T version is currently running?
3. What ZED SDK/driver combination is supported on that version now?
4. Is TERRA AI available under the required licensing/offline deployment terms?
5. Which current ZED outputs should be consumed directly vs via ROS 2?
6. Should the first real Perception API be Python-native, ROS-native, or transport-neutral with ROS adapters?

## Localization

7. For the current UGV, which performs better and is operationally simpler: ZED-native tracking, cuVSLAM, or fused provider?
8. What GNSS/IMU hardware is actually present or ordered?
9. Where should frame transforms and calibration truth live?

## Runtime

10. Should Cognitive Runtime be an in-process PILOT module or a separate local service?
11. What event bus gives the simplest deterministic local architecture?
12. What parts of current `AutonomyCore` should become Skills vs Executive logic?

## Models

13. Which approved non-Chinese candidate gives the best structured planning on AGX Orin 64GB?
14. Do we need one multimodal local model or separate vision/mission models in v1?
15. Which inference engine is most stable on the actual JetPack version?
16. What latency budget should trigger deterministic fallback?

## Storage

17. Which local data must survive every reboot?
18. What storage budget per mission is acceptable?
19. Which experience should auto-delete, compress, or upload?
20. Should local event journal use SQLite-only, MCAP + SQLite, or another combination?

## Fleet

21. Should TRACK remain one ground-station process for v1?
22. Which entities are authoritative locally vs centrally?
23. How should provisional IDs be represented on the wire?
24. What is the minimum viable asset-to-asset communication story?

## Deployment

25. Are containers appropriate for every Jetson component, especially GMSL/ZED drivers?
26. What must remain host-side?
27. Should the first Ansible release deploy systemd services, containers, or a hybrid?
28. What rollback mechanism is achievable before custom Fleet Deployment exists?

## Repository

29. Which proposed folder changes improve boundaries enough to justify moving existing code?
30. Which docs are stale/contradictory today?
31. Is `ARGUS-OS-PLAN.md` still treated as governing spec anywhere in code/tests?
32. Which CI “laws” should be extended for the new architecture?

Claude should record answers as ADRs or open decisions.

---

# 35. Required documentation reconciliation task for Claude

Claude is explicitly authorized to:

- rewrite stale Markdown;
- archive superseded plans;
- rename documentation files where useful;
- update `CLAUDE.md`;
- update `PROJECT.md`;
- update `STATUS.md`;
- update `NEXT-STEPS.md`;
- update/reconcile `ARGUS-OS-PLAN.md`;
- create `ARCHITECTURE.md`;
- create ADRs;
- create Engineering Graph files;
- create subsystem `CLAUDE.md` files **only where they improve local guidance**.

Claude is **not** authorized to:

- silently delete working code simply because the target directory structure differs;
- claim planned architecture is already implemented;
- mark simulated systems as hardware-proven;
- rewrite the frozen LINK contract without a migration/version plan.

When docs disagree:

1. current code/hardware evidence defines **as-built truth**;
2. this architecture defines **target direction**;
3. ADRs explain deliberate deviations;
4. `STATUS.md` states the current gap.

---

# 36. Recommended source-of-truth hierarchy

```text
ARCHITECTURE.md
    target architecture + laws

architecture/decisions/ADR-*.md
    decisions and deviations

architecture/graph/*
    machine-readable component/status/dependency truth

STATUS.md
    generated/current implementation state

NEXT-STEPS.md
    prioritized execution plan

CLAUDE.md
    instructions for AI coding agents

PROJECT.md
    product context/glossary

RESEARCH.md
    research -> Argus decision mapping

DEPLOYMENT.md
    device lifecycle

MODELS.md
    approved model registry/policies

SECURITY.md
    security architecture and controls
```

---

# 37. Suggested Engineering Graph bootstrap

The first graph population should include every current major system.

Illustrative entries:

```yaml
components:
  - id: platform.link
    type: Component
    status: software_verified
    path: link/
    role: shared_contract

  - id: platform.track
    type: Service
    status: software_verified
    path: track/
    role: fleet_world_model

  - id: edge.pilot
    type: Service
    status: simulated
    path: drive/pilot/
    role: edge_runtime
    known_gaps:
      - full_runtime_not_yet_proven_on_jetson

  - id: perception.zed
    type: Adapter
    status: planned
    path: null
    blockers:
      - driver_compatibility
      - hardware_attachment
      - offline_license_verification

  - id: core.cognitive_runtime
    type: Component
    status: planned

  - id: learning.rl
    type: Component
    status: planned
```

Relationships:

```yaml
relationships:
  - from: edge.pilot
    type: USES
    to: platform.link

  - from: platform.track
    type: CONSUMES
    to: platform.link

  - from: perception.zed
    type: IMPLEMENTS
    to: core.perception_interface

  - from: core.cognitive_runtime
    type: CONSUMES
    to: core.local_world_model
```

This is illustrative, not the final schema.

Claude should generate the initial graph from the actual repo.

---

# 38. Suggested first implementation slice

Do **not** try to implement the whole document at once.

The best first slice after architecture/document reconciliation is:

```text
1. Engineering Graph
2. Perception interface refactor
3. Localization provider
4. Local persistent store
5. Real Jetson edge runtime proof
6. ZED integration
7. Real safe UGV navigation
8. Experience recording
```

Only after these are real should Claude build a sophisticated cognitive harness on assumptions.

Why:

> A brain trained on fake senses and fake body interfaces can make the software look advanced while delaying the hardest truth: whether the machine can reliably observe, localize, and act.

---

# 39. Final architecture in one sentence

> **Argus OS is a modular, edge-native autonomy platform that lets machines across Land, Air, and Sea perceive their environment through replaceable sensors, represent reality through a shared ontology, maintain local persistent world state and memory, reason through a model-agnostic cognitive harness, verify and execute typed skills through domain-specific controllers, remain safe and autonomous when disconnected, synchronize into a Maven-like fleet intelligence layer when connected, and continuously improve through a controlled experience/simulation/learning pipeline.**

---

# 40. Final principle for Claude Code

Do not optimize for “more AI.”

Optimize for:

```text
modularity
truth
replaceability
local autonomy
typed interfaces
observability
safety
testability
provenance
controlled learning
```

The Argus moat should not depend on whichever model is popular this quarter.

The enduring product should be:

```text
ONTOLOGY
+ WORLD MODEL
+ MEMORY
+ COGNITIVE HARNESS
+ SKILLS
+ SAFETY
+ EXPERIENCE
+ FLEET INTELLIGENCE
+ HARDWARE/MODEL ABSTRACTION
```

Everything else should be replaceable.

---

# Appendix A — Current audit snapshot that must not be lost

From the supplied as-built audit, as of 17 Aug 2026:

- `Argus_OS` is the active monorepo.
- `Argus_Drive` is archived and copied/diverged into the monorepo.
- `Argus_Ledger` is unrelated.
- LINK/TRACK/PILOT/C2 already exist.
- PILOT has not yet been fully proven running on the Jetson.
- Perception is simulated.
- ZED is not integrated.
- Nav2 is sim-proven, but real sensor data is not feeding costmaps.
- No persistent SLAM map exists.
- WorldSlice is local but memory-only.
- TRACK has a real SQLite-backed fleet world model.
- Disconnection continuation is implemented/tested in software.
- No RL/Isaac/training pipeline exists.
- No real sensor driver or locomotion driver was complete at audit time.
- The teleop path and PILOT path are parallel stacks.
- Local LLM deployment is implemented as an adapter but unproven.
- The real UGV safety state requires hardware/firmware verification before autonomy testing.

Claude must revalidate each of these before treating it as current.

---

# Appendix B — Research and platform source list

Primary/official sources where available:

1. Palantir Foundry Ontology Overview  
   https://palantir.com/docs/foundry/ontology/overview/

2. Palantir Maven / Defense Air & Space  
   https://www.palantir.com/offerings/defense/air-space/

3. Palantir Maven Smart System — 2026 Alliance article  
   https://blog.palantir.com/maven-smart-system-innovating-for-the-alliance-5ebc31709eea

4. NVIDIA Vesta  
   https://research.nvidia.com/labs/gear/vesta/

5. NVIDIA Do What You Say  
   https://research.nvidia.com/publication/2026-06_do-what-you-say-steering-vision-language-action-models-runtime-reasoning-action

6. RISE  
   https://arxiv.org/abs/2602.11075

7. MEM  
   https://arxiv.org/abs/2603.03596

8. VLA-MBPO  
   https://arxiv.org/abs/2603.20607

9. World-Task Factorization  
   https://arxiv.org/abs/2606.02027

10. NVIDIA Isaac Lab  
    https://developer.nvidia.com/isaac/lab

11. NVIDIA Isaac Sim  
    https://developer.nvidia.com/isaac/sim

12. NVIDIA Cosmos  
    https://www.nvidia.com/en-us/ai/cosmos/

13. NVIDIA Nemotron  
    https://developer.nvidia.com/topics/ai/nemotron

14. Google Gemma 4  
    https://ai.google.dev/gemma/docs/core

15. Microsoft Phi-4 Mini model information  
    https://huggingface.co/microsoft/Phi-4-mini-instruct

16. Stereolabs ZED SDK 5 / TERRA  
    https://www.stereolabs.com/blog/introducing-zed-sdk-50

17. Stereolabs TERRA technology  
    https://www.stereolabs.com/our-technology

18. NVIDIA Jetson software update mechanism  
    https://docs.nvidia.com/jetson/archives/r36.5/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html

---

# Appendix C — Questions the founder can ask Argus Engineering Graph later

```text
What is still only simulated?
What has never run on Jetson?
Which components depend on ZED?
What changes if I replace ZED?
What depends on localization?
Which modules can issue physical actions?
Which safety law protects this action?
Which components have no real-hardware validation?
Which open decisions block ZED integration?
Which model is approved for the deployed profile?
What version is Tessy-01 running?
Which research paper led to the memory architecture?
Which ADR created ActionVerifier?
What is the implementation status of Argus Flight?
Which tests prove disconnection behavior?
Which bugs affect the teleop path?
Which components would break if LINK v1 changed?
What is the next highest-priority blocker?
```

If the system cannot answer questions like these, the internal architecture graph is not yet doing its job.

---

# Appendix D — Claude Code operating rule

When Claude encounters ambiguity:

```text
DO NOT GUESS
```

Instead:

1. inspect code;
2. inspect hardware/config if accessible;
3. inspect the Engineering Graph;
4. inspect relevant ADR/research;
5. state the conflict;
6. propose options;
7. mark an OpenDecision;
8. continue on non-blocked work where safe.

The goal is not to eliminate uncertainty.

The goal is to ensure uncertainty is **explicit, queryable, and never silently encoded into the architecture**.
