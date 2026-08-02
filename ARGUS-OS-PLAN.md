# ARGUS OS — Master Build Plan (v1.0)

This document is the single source of truth for building the ARGUS operating system. It is written as a brief for an AI coding agent (Claude Code). Read it fully before writing any code. Where this document and any older artifact disagree, this document wins. The architecture deck "argus-architecture-v9.html" is historical reference only and must not be treated as a spec.

"ARGUS OS" is a placeholder name. A final name will be chosen later. Do not hardcode the name into schemas, package names, or protocols in ways that are expensive to change; use a single configurable constant.

---

## 1. What we are building

ARGUS OS is an operating system for unmanned defence operations. It makes any collection of machines (ground vehicles, drones, vessels, fixed sensors) behave as one coordinated force, commanded by a human operator through a map and voice.

It is an operating system in the architectural sense, not the desktop sense: machines install it, and applications run on it. It consists of:

1. **The contract (ARGUS LINK).** A strict, versioned schema defining what an Entity, Task, and Observation are, and the messages every asset must speak. This is the constitution of the system. Everything else can be rewritten against it.
2. **The world model (ARGUS TRACK).** One live, shared registry of everything known: entities, tracks, assets, zones, missions, their relationships and history. Every sensor writes to it; every asset and application reads from it. Built on the ontology defined in section 3.
3. **The runtime (ARGUS PILOT).** The same core autonomy software installed on every machine. It perceives, navigates, executes tasks, and reports over LINK. Bodies differ only through the HAL (section 6) and a capability manifest.
4. **Core services.** Identity and permissions, secure comms, the AI gateway (section 7), and the voice layer (section 8).

Applications sit on top and consume these through defined interfaces. The first application is **ARGUS C2**: the operator's map, event feed, and voice console. Future applications (Plan, Review, Fleet, third-party apps) reuse the same interfaces. **ARGUS INTEL** is the fifth product of the family: the reports, Q&A, and analytics capability. In this architecture INTEL is not a separate server; it is the AI gateway plus the world model's history, surfaced through applications (the voice Q&A in v1, the Review application and shift reports post-v1). Keep the name in user-facing materials; in code it maps to gateway capabilities.

### What v1 must prove

One UGV, one server, one C2 station:

- A real UGV running PILOT patrols autonomously and appears as a live asset on the C2 map.
- Detections from the UGV become tracks in the world model and appear on the map with plain-language event descriptions.
- The operator issues a task by voice ("Argus, send the vehicle to gate three") and by map click. The vehicle executes it and reports status.
- A simulated vehicle and the real vehicle are indistinguishable to the server.

### Strategic context (why these choices)

- Comparable systems: Anduril Lattice (contract/mesh layer), Palantir (ontology/decision layer), Skydio (onboard autonomy). ARGUS combines all three layers in one sovereign stack.
- The long-term moat is the contract plus the accumulated world model, not any individual model or sensor. Perception components are deliberately swappable.
- The long-term business is a platform: hardware makers integrate their machines via LINK, software partners build applications via the SDK. v1 builds the doors for this without walking through them.
- Open interface, closed core: the LINK protocol and (later) the SDK are intended for eventual open publication so hardware makers integrate cheaply and the contract becomes the standard; the world model, fusion, AI, and runtime remain proprietary. Consequence for code: the `link/` package must stay cleanly separable, with no dependencies on internal TRACK or PILOT code, publishable on its own from day one.

---

## 2. Laws (non-negotiable rules)

These rules override convenience in every implementation decision. Violating one is an architecture bug even if the code works.

1. **The HAL law.** No code above the hardware abstraction layer may reference a specific vehicle type, sensor model, or device. No `if vehicle_type == "ugv"` anywhere in perception, decision, tasking, or comms logic. All body differences live in drivers and capability manifests.
2. **The SDK honesty law.** C2 (and every future application) talks to the world model and assets only through the public service interfaces. No private backdoors, no direct database reads. C2 is application number one on the SDK, and must never use an interface a third-party application could not use.
3. **The gateway law.** No code outside the AI gateway may name a specific AI model or provider. All intelligence requests go through the gateway; providers are swappable adapters.
4. **The schema law.** The ontology and LINK schema are written multi-domain (ground, air, maritime, fixed) from the first line. v1 implements ground only. Adding a domain must never require changing the skeleton, only adding subtypes and drivers.
5. **The waterline law.** Operators never see ontology terminology, schema names, or system internals. The operator-facing surface is: a map, things on the map, plain sentences, and voice. Design target: an operator with one week of training and no technical background.
6. **The disconnection law.** Every asset must be fully functional alone, more useful when connected, and never dependent on the link. Connectivity adds capability; it never enables basic operation. Assets carry a local slice of the world model and merge on reconnect.
7. **The honesty law (voice/AI).** The system never claims more certainty than it has. Confidence is always surfaced in language ("possible person, low confidence"). Spoken output is always also shown as text.
8. **The sovereignty laws.** All deployment targets are air-gapped. No Chinese AI models anywhere in the stack. No cloud dependency in any mission path. Cloud AI adapters are permitted only in development and demo policy profiles, never in deployed profiles.
9. **The licensing law.** Every third-party model, library, and dataset must have its license verified for military use before integration. Known constraint: Meta Llama licenses carve out military use for non-US/non-allied users and are disqualified. Apache 2.0 weights (e.g. Mistral family) are the baseline for local LLMs. When in doubt, flag and ask; do not integrate.
10. **The registry law.** Everything the HAL knows (installed drivers, detected devices, manifests, configuration state) must be queryable structured data, not just code. A future integration copilot will read this registry.

---

## 3. The ontology skeleton

Approach: hybrid, weighted bottom-up. The skeleton below is designed top-down and is frozen once implemented (changes require a version bump and migration). Concrete subtypes are added bottom-up only when a real sensor or deployment produces them. Abstractions come from thinking; specifics come from sensors.

### Base concepts (the skeleton)

All IDs are ULIDs. All timestamps are UTC ISO 8601. All positions are WGS84 lat/lon plus altitude in meters (altitude may be null for ground assets).

1. **Entity.** Anything that exists in the world and is not one of our assets. Has: `entity_id`, `entity_class` (person, vehicle, animal, structure, vessel, aircraft, unknown), `attributes` (open key-value, e.g. color, size), `first_seen`, `last_seen`. An Entity is the durable identity; it may be observed many times.
2. **Observation.** A single report about an Entity by a single sensor at a single time. Has: `observation_id`, `entity_id` (may be provisional), `asset_id` (who saw it), `position`, `confidence` (0 to 1), `entity_class`, `attributes`, `narration` (optional plain-language description), `timestamp`. Observations are immutable.
3. **Track.** The fused, live state of one Entity: current position, velocity, threat assessment, contributing observations, and history. Has: `track_id`, `entity_id`, `state` (active, lost, closed), `position`, `velocity`, `threat_level` (none, low, medium, high), `confidence`, `contributing_assets`, `history`. Tracks are what operators see. Entity resolution (deciding two observations are the same Entity) happens in TRACK and updates Tracks.
4. **Asset.** A machine or sensor that is part of our force. Has: `asset_id`, `asset_class` (ugv, uav, usv, fixed_sensor, base_station), `capabilities` (from its manifest), `status` (active, standby, fault, offline), `position`, `battery`, `current_task_id`, `last_heartbeat`.
5. **Task.** A unit of work assigned to an Asset. Has: `task_id`, `asset_id`, `task_type` (navigate, patrol, hold, follow_track, return_home; extensible), `parameters` (waypoints, target track_id, speed), `priority`, `status` (pending, accepted, running, done, failed, cancelled), `issued_by` (operator identity or system), `timestamps` per state change.
6. **Zone.** A named geographic region with meaning. Has: `zone_id`, `name` (operator-facing, e.g. "Gate 3"), `geometry` (polygon), `zone_type` (protected, restricted, patrol_route, home), `rules` (optional, e.g. alert on entry).
7. **Mission.** A grouping of Tasks toward one objective, with ordering and contingencies. Has: `mission_id`, `name`, `objective` (plain language), `task_ids`, `status`. v1 uses Missions minimally (a patrol is a one-task mission); the concept exists so multi-asset plans have a home.
8. **Relationship.** A typed link between any two objects above. Has: `relationship_id`, `subject_id`, `predicate` (seen_with, same_as, responding_to, inside, escalated_from; extensible), `object_id`, `confidence`, `timestamp`. This is the graph that accumulates operational intelligence over time.

### Rules for the ontology

- The skeleton (these 8 concepts and their required fields) is versioned as `ontology_version` and carried in every message.
- Subtype vocabularies (`entity_class` values, `task_type` values, `predicate` values) are open enums: unknown values must be preserved and passed through, never dropped. This is how domains grow without skeleton changes.
- Every operator-facing string (zone names, narrations, event sentences) lives in data, not code, so language and terminology can change per deployment.

---

## 4. The LINK contract

Protobuf is the source of truth for all message and object schemas. Generated code is used everywhere; no hand-written parallel definitions. A single `link/` proto package defines the ontology objects (section 3) and the five messages below. REST/JSON representations are generated or mapped mechanically from the protos for the C2/web side.

### The five messages

Direction is relative to the asset. Field types follow section 3 objects.

1. **HEARTBEAT (asset to platform, periodic, default 1 Hz).** `asset_id`, `asset_class`, `status`, `battery`, `position` (coarse), `current_task_id`, `ontology_version`, `timestamp`. Purpose: liveness and fleet status. Loss of N heartbeats marks the asset offline and triggers replanning hooks.
2. **TELEMETRY (asset to platform, periodic, default 5 to 10 Hz when moving).** `asset_id`, `position`, `heading_deg`, `speed_mps`, `payload` (open, per-manifest extras like camera gimbal state), `timestamp`.
3. **OBSERVATION (asset to platform, event-driven).** The wire form of the Observation object: everything an asset reports about the world. Smart assets (running PILOT) send fully-formed Observations with class, confidence, and optional narration. This message was called ENTITY_EVENT in older material; the name is now OBSERVATION to match the ontology.
4. **TASK (platform to asset).** The wire form of the Task object. Assets must acknowledge with TASK_STATUS(accepted) or TASK_STATUS(failed, reason) within a timeout.
5. **TASK_STATUS (asset to platform, event-driven).** `task_id`, `status`, `progress` (0 to 1), `eta_sec`, `message` (plain language, operator-visible), `timestamp`.

### Transport

- Transport is abstracted behind comms drivers (section 6). The contract is transport-agnostic by design.
- v1 reference transport: MQTT (Mosquitto broker) for all five messages, topic scheme `argus/{asset_id}/{message_type}` upward and `argus/{asset_id}/task` downward, Protobuf-encoded payloads.
- Live video is out of band: WebRTC from asset to C2, negotiated via the platform, displayed picture-in-picture. Video never flows through the world model.
- Same protocol must run unmodified over WiFi, mesh radio, or satellite in future; nothing in the schema may assume transport properties beyond eventual delivery and possible disconnection.

### Contract discipline

- The contract is versioned (`link_version`). v1 is frozen before any dependent code is written; changes after freeze require an explicit version bump and a migration note in this document.
- Every field is documented in the proto with a comment stating meaning, units, and who sets it.
- A `link/README.md` explains each message in one plain-English paragraph. This doubles as the first partner-facing document.

---

## 5. System components

### ARGUS TRACK (the world model server)

- Stack: Python, FastAPI, Redis (live state and pub/sub), plus an embedded persistent store (SQLite in v1) for history, entities, zones, relationships.
- Consumes: HEARTBEAT, TELEMETRY, OBSERVATION from the MQTT broker.
- Does: asset registry maintenance, observation-to-track fusion (v1: nearest-neighbor association with time and distance gates; design the association module as swappable), track lifecycle (create, update, mark lost, close), zone rule evaluation (entry/exit events), relationship writes, event feed generation (plain-language sentences from templates).
- Serves (the service interfaces that later become the SDK): 
  - REST: CRUD and query for entities, tracks, assets, tasks, zones, missions, history.
  - WebSocket: live streams of track updates, asset updates, events.
  - Task issuing endpoint (validates, persists, publishes TASK to the asset's topic).
- All interfaces enforce the identity/permissions service (v1: simple token-based roles, operator vs admin; the enforcement point must exist even while the policy is trivial).

### ARGUS C2 (application number one)

- Stack: React, Vite, Leaflet (dark tiles), WebSocket client, WebRTC for video PiP.
- Screens: one. Map center; left rail force list; right rail event feed; bottom voice bar with push-to-talk, live transcription, and printed replies. Overlays (camera PiP, track detail) open over the map and close back. No nested navigation. An app-shell launcher (Operate, Plan, Review, Fleet, Admin) is designed into the frame but only Operate exists in v1; the others are visible but disabled.
- Consumes only the TRACK service interfaces and the voice service. Enforced by the SDK honesty law.
- Color language, fixed: green healthy/friendly, amber attention, red act now, gray offline. No other status colors.
- Design references: Anduril Lattice UI, ATAK. Dark theme always. Fonts and brand per the ARGUS brand guidelines (JetBrains Mono, IBM Plex Sans, self-hosted, no CDN).
- **The OS's own UI:** the app-shell launcher and the Admin surface are the operating system's user interface (the equivalent of an OS's home screen and settings). They belong to the OS, not to any application. v1 ships the launcher frame (only Operate enabled) and a minimal Admin page (zones, assets, users, AI policy profile display) behind the admin role. Fleet health beyond the C2 left rail is post-v1.
- **Founder review gates for frontend:** the founder reviews and approves (1) the C2 layout and visual direction at Stage 2 start, before implementation, using updated mockups; (2) each major C2 surface (map interactions, event feed, voice bar) as built; (3) the Stage 5 brand-polish pass; (4) the OS-level UI: the launcher shell's layout and visual direction before it is first implemented, and the Admin surface before it is built. Frontend work, application-level or OS-level, does not proceed past a gate without explicit approval. The layout descriptions in this document (map center, left force rail, right event feed, bottom voice bar, fixed four-color status language, launcher as a grid of role icons) are the approved initial direction; propose mockups within it at each gate for founder review.

### ARGUS PILOT (the edge runtime)

- Stack: ROS2 Humble, Nav2 (MPPI controller) for navigation; TensorRT for detection; ZED SDK for the camera; rosbag2/MCAP for recording; Foxglove for debugging.
- Reference hardware (v1): Jetson AGX Orin 64GB, ZED X via GMSL2, the Jeep-chassis 4x4 electric UGV. Production later targets Jetson AGX Thor. Nothing above the HAL may assume Jetson.
- Structure: 
  - **Perception**: ZED-based depth/detection pipeline producing standardized Observations. Detector: YOLO-class model via TensorRT with custom ONNX ingest. Perception is a swappable module behind a defined interface (the platform's sovereignty story depends on this).
  - **Localization**: GPS-fused with GNSS-denied fallback. Open decision (section 10): cuVSLAM vs ZED-native localization; exactly one becomes the source of truth.
  - **Autonomy core**: task execution state machine (receive TASK, plan, execute via Nav2, report TASK_STATUS), local world-model slice, disconnection behavior (continue current task, queue observations, merge on reconnect).
  - **LINK client**: speaks the five messages through the comms driver.
- The simulated vehicle: a Python process (paho-mqtt) implementing the same LINK client and task state machine with fake movement and scripted observations. It is a permanent test fixture, not a throwaway; CI runs against it.

### Identity and permissions (core service, minimal v1)

- v1: token-based auth, two roles (operator, admin), every TRACK interface checks it. Admin functions (zones, assets, users, AI policy) are separated from operator surfaces now, because retrofitting permission boundaries after third-party apps exist is not feasible.

---

## 6. The HAL (hardware abstraction layer)

Lives inside PILOT. Three driver interfaces plus the manifest:

1. **Locomotion drivers.** Interface: `set_velocity(linear, angular)`, `goto(waypoint)` primitives consumed by Nav2's controller layer; driver translates to the platform (v1: the UGV's motor controller; interface designed so a rotor or rudder driver is additive).
2. **Sensor drivers.** Interface: standardized outputs only (images with intrinsics, point clouds, GNSS fixes, IMU) into the perception and localization modules. v1 drivers: ZED X, GNSS, IMU.
3. **Comms drivers.** Interface: `publish(message)`, `subscribe(topic, handler)`, connection-state events. v1 driver: MQTT over WiFi. Mesh radio and satellite are future drivers behind the same interface.

**The capability manifest.** A per-machine YAML file: asset_class, dimensions, max speed, turn constraints, can_hover, battery capacity, installed sensors, installed drivers. The autonomy core reads it at boot and adapts. No code changes per machine.

**The registry.** The HAL exposes, as queryable structured data: installed drivers and versions, manifest contents, detected devices (bus scan results), configuration state, and driver health. Served locally on the asset and mirrored into TRACK's asset record. This is the substrate for the future integration copilot.

Porting to machine #2 must consist of: write or reuse drivers, write a manifest, flash the same runtime. If it requires more, the HAL has failed and the design must be corrected before proceeding.

---

## 7. The AI gateway (core service)

One service through which all intelligence requests flow. Callers send capability-level requests ("summarize this track history", "convert this transcribed order into a Task", "draft a shift report"), never model-level requests.

- **Adapters (model providers as drivers):** `anthropic` (Claude API), `openai`, `local` (vLLM or llama.cpp serving Apache-2.0 weights, Mistral family as baseline). Adding a provider is adding an adapter; no caller changes.
- **Policy profiles:** the deployment profile whitelists adapters. `deployed` profile: local only, cloud adapters not installed. `dev`/`demo` profiles: cloud permitted. Profile is set at install time by an admin, not togglable by operators.
- **v1 scope:** the gateway exists with the local adapter working and one cloud adapter for bench development; used by the voice layer (intent parsing, response generation) and event-sentence enrichment. Mission-planning AI and the integration copilot are post-v1 applications of the same gateway.
- **Two AI roles, kept distinct in design:** mission-time AI (operator-facing, disciplined, honesty law applies in full) and admin-time AI (the future integration copilot that reads the HAL registry and assists setup; bench-time, cloud-permitted).

---

## 8. The voice layer

- Pipeline: local STT (Whisper-class), intent handling through the AI gateway, local TTS. Push-to-talk from C2. Everything heard and everything spoken is printed in the voice bar (honesty law, audit trail, noisy-environment redundancy).
- **Character sheets:** the personality is a data file (system prompt plus phrasing rules), not code. Two ship in v1: `ops` (terse, formal, radio-operator discipline; the default) and `demo` (measured charm for demonstrations). Modular and swappable per deployment; adding personalities is adding files.
- Voice can: answer questions about the world model ("what's happening at gate three"), issue tasks (with confirmation readback before execution: "Confirm: send UGV-1 to gate three?"), and report status. Voice cannot: execute anything without readback confirmation, or claim certainty beyond track confidence (honesty law).
- All voice-issued tasks pass through the same task endpoint as map-issued tasks, with `issued_by` recording the voice path and operator identity.

---

## 9. Build sequence and definitions of done

Build in this order. Each stage has a definition of done; do not proceed past a failed definition.

**Stage 1: The constitution.**
Write the ontology protos and the five LINK messages, with full field documentation and the plain-English `link/README.md`. Freeze as `link_version 1`.
Done when: protos compile, generated Python and TypeScript bindings build, README reads correctly to a non-engineer.

**Stage 2: The world model plus the fake army.**
TRACK server (ingest, fusion, registry, REST, WebSocket, task endpoint) plus the simulated vehicle plus a minimal C2 map page (dark map, live asset icon, live tracks, click-to-task). C2 and TRACK are built in parallel deliberately: C2 stress-tests the interfaces, and interface friction found here is fixed here, before the SDK hardens.
Done when: the simulated vehicle appears on the map, moves, produces observations that become visible tracks, accepts a map-issued task, and reports progress to completion. Kill the sim mid-task: the asset goes gray on lost heartbeats and the task is marked failed.

**Stage 3: Steel.**
PILOT on the real UGV: HAL drivers (ZED X, GNSS/IMU, motors, MQTT), perception producing real Observations, localization decision made and implemented, Nav2 executing navigate and patrol tasks, disconnection behavior working.
Done when: the server cannot distinguish the real UGV from the simulated one by message inspection; the UGV completes a patrol task outdoors with at least one correct person-detection becoming a track in C2; pulling the network cable mid-patrol does not stop the patrol, and reconnection merges queued observations.

**Stage 4: The voice.**
Voice layer in C2 through the AI gateway, ops character sheet, task issuing with readback confirmation.
Done when: an operator with no briefing beyond "push to talk" can ask what is happening and send the vehicle to a named zone by voice; every exchange is printed; a deliberately ambiguous order results in a clarifying question, not an action.

**Stage 5: Hardening for demonstration.**
Event-feed language polish, C2 visual polish to the brand guidelines, install/run documentation, demo script (the 15-minute flow: map, patrol, detection, voice tasking, disconnection resilience).
Done when: a cold start from documented steps to a running demo takes under 30 minutes, twice in a row, by someone other than the author.

Throughout: the simulated vehicle runs in CI against every TRACK and LINK change. Any commit that breaks the sim's full task loop is a broken commit.

---

## 10. Open decisions (flag, do not silently resolve)

1. **Localization source of truth:** cuVSLAM vs ZED-native. Decide at Stage 3 start with a short bench comparison on the actual vehicle. Exactly one wins; do not run both.
2. **ZED SDK / Terra licensing for production:** offline/air-gapped activation terms and per-unit field licensing are unverified with Stereolabs. Perception stays behind its interface partly because of this. Verify before any production commitment.
3. **Detector model and version:** choose at Stage 3 based on current best available with acceptable license; do not inherit choices from older documents.
4. **The name:** ARGUS OS is a placeholder throughout.
5. **Drive/Flight product structure** (shared core vs independent lines): does not block v1; the schema law keeps both open. Decide when the second body type is scheduled.

## 11. Build tooling: model selection

Guidance for the human and the coding agent. The coding agent cannot change its own model; the founder switches with `/model`. The agent's duty is to flag when a switch is warranted, per the escalation protocol below.

- **Stage 1 (ontology and LINK protos): Fable 5.** The schema is the most expensive artifact to get wrong; use the most capable model and accept the cost.
- **Stages 2 to 5 (all implementation): Opus 5**, default effort for routine work, xhigh effort for fusion logic, the PILOT task state machine, and disconnection/merge behavior.
- **Escalation protocol:** if the current model has examined the relevant code and evidence and still cannot resolve a design or debugging problem after two serious attempts, the agent must stop and state: "This meets the escalation criteria; recommend switching to Fable 5 for this task," rather than iterating further. The founder decides.
- **De-escalation:** mechanical work (boilerplate, file moves, formatting, repetitive test scaffolding) may be delegated to cheaper models or subagents at the founder's discretion; never for schema, fusion, or autonomy logic.
- This section reflects the model lineup as of August 2026 and should be revisited as models change.

## 12. Out of scope for v1 (doors built, rooms empty)

- Second body types (drone, vessel, tower): in schema and HAL interfaces only.
- The SDK as a published artifact: the service interfaces are the SDK's raw material; formal extraction, docs, and versioning happen after Stage 5.
- Integration copilot: enabled by the registry law, built later.
- Multi-operator, multi-station, federation between base stations.
- Mission planner AI, Plan/Review/Fleet applications (launcher shows them disabled).
- On-vehicle voice interaction.
- Partner app catalog, certification, distribution.

---

*End of plan. First Claude Code instruction: "Read ARGUS-OS-PLAN.md fully. Begin Stage 1: create the ontology and LINK protos exactly as specified in sections 3 and 4, then stop for review before Stage 2."*
