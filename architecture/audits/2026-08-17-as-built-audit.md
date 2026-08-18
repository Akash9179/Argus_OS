# Argus As-Built — Architecture Audit

**Code-derived audit · no changes made · prepared for review by an outside architect.**
What has actually been built in the Argus repositories as of 17 August 2026, read from the code rather than the documentation. Claims cite files; where the code and the plan disagree, the code is reported.

- Repos: **Argus_OS** (active) · **Argus_Drive** (archived) · **Argus_Ledger** (unrelated)
- Tests: **141 pass / 1 fail** (a bridge-daemon race, see §9)
- Audited: 2026-08-17, at Argus_OS main @ `3c26521` (2026-08-11)
- Independently reviewed against the code by a second model (Fable 5), 2026-08-17; four corrections and one added risk incorporated.

---

## §1 · What Argus is currently being built to do

Argus is an **operating system for unmanned defence operations**: install the same runtime on any machine (ground vehicle, drone, vessel, fixed sensor), and the fleet behaves as one coordinated force commanded by a human through a map and voice. The governing spec is `Argus_OS/ARGUS-OS-PLAN.md`, which the code follows closely. The stated positioning is deliberate: Anduril Lattice's contract/mesh layer + Palantir's ontology layer + Skydio's onboard autonomy, in one sovereign, air-gapped stack. The intended moat is the *contract plus the accumulated world model*, not any model or sensor — perception is deliberately swappable.

Three repos share the `~/Projects/Argus` directory, and only one is the product:

- **Argus_OS** — the monorepo. Everything below is about this repo.
- **Argus_Drive** — a pre-laws browser teleop cockpit + bench brain, archived 2026-08-06 (`MOVED.md`). Its code was copied into `Argus_OS/drive/`; the copies have already diverged from the archive.
- **Argus_Ledger** — an unrelated accounting app. Excluded from this audit.

Ten "laws" (HAL, SDK honesty, gateway, schema, waterline, disconnection, honesty, sovereignty, licensing, registry) are not aspirational — most are **enforced by tests** (e.g. a test fails if a model name appears outside `gateway/adapters/`, or if a cloud adapter appears in the `deployed` profile).

Build stages: S1 (contract) ✓, S2 (world model + sim + C2) ✓, S3A (edge runtime above drivers) ✓, S4 (voice) ✓, S5 partially done. S3B (real hardware drivers) is **blocked on steel** — and per the 2026-08-11 hardware survey, the near-term demo target has shifted to **manual teleop**, because the real vehicle has no sensors at all.

## §2 · Current high-level architecture and communication

Four planes, joined by one frozen contract:

1. **LINK** (`link/`) — the constitution. Protobuf ontology (8 objects: Entity, Observation, Track, Asset, Task, Zone, Mission, Relationship) plus five wire messages (HEARTBEAT, TELEMETRY, OBSERVATION, TASK, TASK_STATUS). Frozen at v1; CI runs `buf breaking` against the `link-v1` git tag. Generated Python and TypeScript bindings; the Python package is installable standalone (`link-contract`). Vocabularies (entity_class, task_type, predicate…) are *open enums* — unknown values are preserved, never dropped.
2. **TRACK** (`track/`) — the world model server. Python/FastAPI. Consumes the four upward messages over MQTT (protobuf payloads, topics `{prefix}/{asset_id}/{kind}`), fuses observations into tracks, evaluates zones, generates an event feed from language templates, and serves REST + WebSocket. Persists to SQLite (protobuf blobs + query columns); Redis is a live fan-out bus with an in-process fallback. The only downward path is `issue_task`, publishing TASK to the asset's topic.
3. **PILOT** (`drive/pilot/`) — the edge runtime installed on every machine. Boots from a per-machine YAML manifest, loads drivers through the HAL, runs one autonomy loop (`AutonomyCore`), navigates via a pluggable Navigator (direct waypoint-following, or Nav2 inside a ROS 2 Humble container), and speaks LINK through a comms driver. Serves a local registry HTTP interface on `:8200`.
4. **Applications** — **C2** (`c2/`, React/Vite/Leaflet) consumes only TRACK's public REST/WS interfaces ("application number one on the SDK"); **voice** (`voice/`) is a separate FastAPI service that reaches TRACK over HTTP with the operator's own token and reaches all models through the **AI gateway** (`gateway/`).

A **parallel teleop stack** exists beside this: `drive/cockpit/` (browser driving UI) ⇄ `drive/bridge/` (vehicle WebSocket daemon with watchdog) ⇄ a `VehicleAdapter` (mock only today). It uses its own JSON wire contract, not LINK; an optional `LinkReporter` feeds the driven vehicle's heartbeat/telemetry into TRACK so it appears on the map. Note: docs mention WebRTC video; **no WebRTC exists in code** — the bridge is a hand-rolled WebSocket server, and video is not implemented.

## §3 · What runs locally vs what depends on cloud

**Everything in the mission path runs locally.** TRACK, C2, voice, gateway, MQTT, Redis, SQLite are all local processes. C2 even renders its own map tiles procedurally (`c2/src/map/terrain.ts`) because air-gapped targets have no tile server.

Cloud appears in exactly two places:

- **The Anthropic adapter** (`gateway/adapters/anthropic_cloud.py`) — permitted only under the `dev` and `demo` policy profiles. The `deployed` profile (the default, chosen fail-closed) refuses cloud at the point of use via each adapter's self-declared `leaves_the_machine` flag, redundantly with the profile allowlist; the `anthropic` SDK isn't even in `requirements.txt` — it lives in `requirements-bench.txt`, so a deployed image doesn't carry the dependency. CI deliberately runs without it.
- **The brain prototype** (`drive/brain/`) — a Node service calling the Anthropic SDK directly with a hardcoded `claude-opus-5`. Flagged in its own README as prototype-only and a gateway-law violation to be fixed.

Speech (whisper.cpp STT, Piper TTS) is fully local and exercised on every profile. The **local language path** (`llama_local`, OpenAI-compatible endpoint, no default model by licensing-law design) is written and configured but **has never answered a request** — the air-gapped LLM story is unproven, and the code says so in its own docstrings.

Important caveat: **PILOT and the OS runtime have never run on the Jetson.** One drive-side component has: the bridge relay (`drive/bridge/argus_relay.py`, deliberately stdlib-only for the Jetson) was proven over a 271 ms relayed link at 15 Hz with 0.4% CPU on the Orin (`STATUS.md`). Note the repo contradicts itself here — `CLAUDE.md` (2026-08-03) still says "No Jetson has ever run any of this," while the newer `STATUS.md` (2026-08-11) records the relay proof. Everything else "local" today means the developer's Mac and CI containers.

## §4 · Perception as implemented

**All perception is currently simulated.** The implemented pipeline:

- `SensorDriver.poll() → list[Detection]` — a Detection carries `entity_class`, `confidence`, north/east offsets *relative to the machine*, open attributes, and a narration string. Sensor drivers never know where they are; the autonomy core geo-projects offsets into WGS84 using the machine's pose, resolves a local entity identity in its `WorldSlice`, and emits a contract Observation.
- The only sensor driver is `SimulatedCamera`, which "sees" scripted sightings declared in the machine's manifest YAML.

Status of the real perception stack:

- **ZED / ZED SDK** — *not integrated.* No ZED driver exists anywhere in the repo. The survey found ZED SDK 5.4.1 installed on the Jetson but its bundled ZED X GMSL drivers target L4T 35.x and will not load on the flashed 36.5 kernel — and **no camera is physically attached** (no `/dev/video*`, no GNSS, no IMU). Air-gapped SDK licensing is unverified with Stereolabs (open decision 2; the email is drafted in `NEXT-STEPS.md` and marked unsent).
- **Object detection** — *decided, not built.* RF-DETR, Apache-licensed tiers only, chosen 2026-08-03 for sovereignty + licensing reasons (YOLO is AGPL; most permissive DETRs are Chinese-origin). Zero detector code exists; TensorRT appears nowhere; the PILOT container base (`ros:humble-ros-base`) carries no CUDA.
- **ROS 2 / Nav2** — *built, sim-proven.* ROS 2 Humble + Nav2 (MPPI) run in Docker; a `LocomotionBridge` node translates `/cmd_vel` ⇄ the HAL locomotion driver and publishes `/odom` + TF from `driver.pose()`, over a local-tangent-plane datum fixed at boot. CI runs real Nav2 route tests in the container. Note Nav2's costmaps currently receive **no sensor input at all** — there is no ROS path from any SensorDriver into perception or costmaps (`nav2.yaml` lists only an inflation layer; a comment says Stage 3B adds a voxel layer).
- **Depth, point clouds, images** — *no interface.* The plan promises sensor drivers emitting "images with intrinsics, point clouds, GNSS fixes, IMU," but the *implemented* interface carries only finished Detections. Raw sensing has no channel through the HAL as coded (see Risks).
- **Localization** — *deferred.* Pose comes from `LocomotionDriver.pose()` (dead-reckoned in the sim driver). cuVSLAM vs ZED-native is an open decision deferred to Stage 3B; design intent is that settling it is "a driver change."
- **Mapping** — no SLAM, no persistent maps. Nav2 runs against odom-only costmaps; TRACK's zones are operator-drawn polygons, not sensed maps.

## §5 · The hardware abstraction layer

**Yes — and it is the most rigorously executed part of the codebase.** `drive/pilot/hal/` implements:

- **Three driver protocols** (`interfaces.py`): Locomotion (`set_velocity`, `goto`, `stop_moving`, `pose`), Sensor (`poll`), Comms (`publish`/`subscribe`/`connected`/`on_connected`). Nothing above them names a vehicle, camera model, or bus. Units, sign conventions, and failure semantics are documented at the interface.
- **Capability manifests** (`manifest.py`, `manifests/*.yaml`) — per-machine YAML declaring identity, speed/turn/accel limits, dimensions, battery, supported task types, and which drivers to load with what settings. Unknown keys are preserved into `extras` and mirrored upward. A second manifest (`ugv-light.yaml`) exists specifically to prove behavior changes with zero code change (Stage 3A criterion 4, in CI).
- **A registry** (`registry.py`) — drivers, versions, devices, live health, and configuration-in-force as queryable structured data, served locally on `:8200` and mirrored into TRACK's asset record via `Telemetry.payload["registry"]` (sent on change only).
- **A loader** (`loader.py`) — name→factory registry; a manifest naming an absent driver refuses to boot.

Real drivers that exist: `mqtt_comms` (real MQTT over WiFi) and the simulated set. No real locomotion or sensor driver exists yet.

The same pattern is applied to **models** (gateway adapters ≙ drivers, policy profiles ≙ manifests) and to **transports** (TRACK's `Transport` protocol with MQTT and in-memory implementations). Two caveats: the teleop bridge has its own separate `VehicleAdapter` abstraction that is *not* the HAL, and localization has no interface of its own — it hides inside `LocomotionDriver.pose()`.

## §6 · How decisions are made after perception

Decision-making is deterministic state-machine logic, split across two layers by what each can know (plan decision 10):

- **On the machine** (`pilot/autonomy/core.py`): a single loop drains orders, refuses task types not in its manifest ("in words, never dropped"), builds a waypoint route, hands it to the Navigator, reports ACCEPTED → RUNNING (progress every ≥5%) → DONE/FAILED/CANCELLED, senses, heartbeats. No branching on machine type anywhere; everything variable comes from the manifest.
- **On the platform** (`track/worldmodel.py`): per-asset autonomy mode, `manual` | `automatic`, stored and *enforced* in TRACK. In automatic, a new (or newly uninvestigated) track triggers `investigate()`: nearest eligible machine (automatic, online, idle, declares `navigate`) is sent a navigate task via the same `issue_task` path a map click uses, with issuer channel `automatic`. Switching back to manual withdraws only the platform's own orders. A language file offering a mode nothing enforces is refused at startup.

**No LLM is in any acting decision loop.** Voice orders always require a human readback confirmation (enforced structurally: `confirm()` is the only path that acts). The bench brain can propose one bounded drive nudge (throttle ≤ 0.35, ≤ 1200 ms, human override always wins) — and that is a prototype outside the OS proper.

## §7 · The world model / shared representation

**Yes, it exists and works.** Two tiers:

**TRACK (fleet truth).** The 8-object ontology stored in SQLite as protobuf blobs with lifted query columns. Fusion (`track/fusion.py`): identity-first association (an asset re-reporting the same entity_id wins over geometry), then nearest-neighbor within 40 m / 30 s gates behind a swappable `Associator` protocol; class-compatibility never enumerates the vocabulary, so unknown classes still associate. Track confidence is an exponentially-weighted blend capped at 0.99 ("never claims certainty"). Entity aliasing writes `same_as` Relationship edges — the beginnings of an intelligence graph. Lifecycle: active → lost (15 s) → closed (300 s), swept by a watchdog. Zone entry/exit is evaluated per update; every operator-visible sentence comes from `event_templates.yaml`, not code.

**WorldSlice (per-machine truth).** Deliberately small: locally-identified entities (same class within 12 m = same thing, forgotten after 30 s), the current task, and home. Local identity is provisional; the wire does not mark it so — TRACK treats asset-assigned IDs as provisional *by convention*, a gap the code itself flags in a docstring.

## §8 · Memory and state mechanisms

| Mechanism | Where | Holds |
|---|---|---|
| SQLite (`var/track.db`) | `track/store.py` | Assets, immutable observations, tracks (200-point in-blob history), tasks (full status history), zones, missions, relationships, events, mirrored registries, autonomy modes, investigation records, entity aliases, zone membership |
| Redis pub/sub | `track/live.py` | Live envelopes (asset/track/task/event updates) for WebSocket fan-out; in-process fallback when Redis is absent |
| Offline queue | `pilot/link_client.py` | Up to 500 observations held through link loss (oldest dropped first), flushed + registry re-sent on reconnect; merge preserves original timestamps (CI-tested) |
| WorldSlice | `pilot/autonomy/worldslice.py` | Machine-local entities, current task, home position — all in-memory, lost on reboot |
| Language / character / policy data files | `*/data/*.yaml` | Every operator-facing sentence, voice personalities, AI policy profiles, event templates |
| Logs | `var/*.log` | Ad-hoc process logs. The bridge daemon has **no logging at all** (flagged in STATUS.md as a pre-incident gap) |

Not present: rosbag2/MCAP recording (planned, unimplemented), historical map storage, any learned or long-term memory, any on-machine persistence of the world slice.

## §9 · Autonomy: real vs placeholder

| Capability | Status | Evidence |
|---|---|---|
| Task state machine (navigate/patrol/hold/return_home, refuse-in-words, cancel) | **real** | CI, two independent implementations (sim + PILOT) |
| Waypoint navigation, direct | **real** | `DirectNavigator`, in-process CI |
| Nav2 (MPPI) navigation with manifest-derived constraints | **real, sim drivers** | Containerized CI drives a machine through real Nav2 |
| Disconnection: continue task, queue, merge on reconnect | **real** | Stage 3A criterion 3, in CI |
| Fleet auto-investigation (automatic mode) | **real** | `worldmodel.investigate()` + tests |
| Voice command with readback | **real (dev profile)** | 701-line test file; cloud LLM only so far |
| Perception (camera, detection, depth) | **simulated only** | Scripted sightings in manifests |
| Localization | **dead reckoning only** | cuVSLAM vs ZED undecided; no GNSS/IMU driver |
| Obstacle avoidance on a real machine | **absent** | Costmaps receive no sensor data |
| Real locomotion | **absent** | MCU relay map unverified; firmware only just obtained |
| Air-gapped language model | **written, never run** | `llama_local`: "real and unexercised" |
| Onboard LLM brain | **bench prototype** | Direct SDK, outside gateway, both repos |

The one failing test (`test_bridge_daemon.py::test_second_client_is_spectator`) is a driver/spectator promotion race — the test sends both clients' auth frames without waiting for the first role assignment, and the daemon's by-design first-auth-wins logic promotes whichever thread arrives first. This reads as a *test* bug (unserialized auths) rather than a daemon defect, but it sits in the safety-adjacent teleop path and is worth fixing rather than ignoring.

## §10 · Navigation, planning, control, and failsafe

**Planning/control:** TRACK issues tasks; the core builds routes (patrol closes its loop, laps via open `extras`); the Navigator abstraction hides whether Nav2 or direct waypoint-chasing executes. `Nav2Navigator.apply_manifest()` pushes the booted machine's own speed/turn/accel/footprint into Nav2's parameter servers at runtime — and honestly reports which parameters Nav2 refused, so a machine can say it is "navigating on numbers that are not its own."

**Safety layers, platform side:** TRACK's watchdog marks assets offline after 5 s of heartbeat silence and fails their open tasks; unacknowledged tasks fail after 10 s; a navigator that gives up reports FAILED rather than staying RUNNING forever.

**Safety layers, teleop side:** the bridge watchdog is a strict STOPPED / DRIVING / LATCHED machine (700 ms silence or link loss while driving → safe-stop and latch; re-arm is explicit and never automatic); ignition triggers self-test checks that gate arming; the mock enforces no-motion-without-ignition-and-gear.

> **The real vehicle, today.** The 2026-08-11 survey and firmware read establish: the deployed MCU firmware **holds its last throttle command forever on link loss** (no timeout of any kind); the steering feedback sensor is disconnected, so held steering commands run the actuator into its mechanical stop; both brake relays are disconnected; there is no ignition or e-stop relay; and drive is the de-energized default. A v4 replacement firmware (`bodies/ugv-01/firmware/`) adds an opt-in latching watchdog and break-before-make on both reversing relay pairs — carefully designed, **written but never flashed or bench-verified**. The relay map itself is verbal and unverified. Nothing in Argus software can currently make this vehicle safe; the fix is at the firmware and bench level, and the repo says so plainly.

## §11 · What happens when the network disappears

The disconnection law ("every asset fully functional alone; link adds, never enables") is implemented, not just stated:

- The autonomy core *never checks* whether the link is up — by design, so behavior cannot differ when watched. The current task runs to completion; observations queue (bounded at 500, freshest kept); on reconnect everything flushes with original timestamps and the registry is re-offered. CI-tested by cutting the comms driver mid-task.
- TRACK degrades gracefully: Redis missing → in-process bus; MQTT reconnection is the driver's problem.
- Cloud loss is a non-event by construction: nothing in a mission path touches cloud. The only genuinely unproven leg is that a fully air-gapped deployment currently has **no working language model** — voice degrades to "cannot think" sentences while map, tasking, and speech (local whisper/piper) continue.
- Limits: C2 needs TRACK reachable (they share the ground station's local network); a machine's world slice is memory-only; there is no asset-to-asset mesh — offline machines are individually functional but mutually invisible.

## §12 · Land, Air, and Sea

**One reusable core with domain-specific modules — by schema and by seam, not yet by implementation.** The ontology is multi-domain from line one: `asset_class` is an open string (ugv/uav/usv/fixed_sensor documented), Position carries optional altitude, Velocity carries `vertical_mps`, manifests carry `can_hover`, and the HAL claims a rotor or rudder driver is additive behind the same two locomotion calls. Fusion and TRACK never branch behaviorally on asset class (checked by inspection; the only `asset_class` conditional above the HAL is an optional query-filter presence check in `track/api.py`, not domain logic). Only ground is implemented.

Known, deliberately-recorded debts for the air domain: zones have no vertical extent (an overflight triggers ground-zone rules); fusion's distance gate ignores altitude (two objects vertically separated would merge); the navigator ignores waypoint altitude and logs a warning saying so. Whether Drive and a future Flight are one product line or two is explicitly open (plan decision 7).

## §13 · Agent / LLM / orchestration architecture

The implemented shape is a **capability gateway, not an agent framework**:

- **Gateway** (`gateway/`): four capabilities — `transcribe`, `speak`, `understand_order`, `answer_question`. Adapters register on import (same pattern as HAL drivers): `anthropic` (Claude, structured output via JSON schema), `llama_local` (OpenAI-compatible endpoint, no default model until a license is verified), `whisper_local` + `piper_local`. Policy profiles pick adapters per capability in preference order; sovereignty is enforced per-request against each adapter's own `leaves_the_machine` declaration, and `check()` publishes a whole-deployment `anything_leaves_the_machine` verdict (True/False/None — None meaning "unverifiable," which a deployed target must treat as failure).
- **Voice** (`voice/`): STT → a strict intent JSON schema (question / order / unclear — no other outcome is legal) → every LLM-named machine and place is re-validated against what TRACK actually contains (a hallucinated machine becomes a clarifying question, never an action) → readback → confirm → the ordinary task endpoint with the operator's own token. ULIDs are deliberately kept out of prompts so a model cannot echo an internal ID into an operator's ear. Personalities are YAML character sheets.
- **Brain prototype** (`drive/brain/`): vision + telemetry + preflight context → one Claude call → speech + optional bounded drive intent, with hard caps and pure-function human-override logic (`assistLoop.ts`). Direct SDK, hardcoded model, acknowledged law violation, not wired into the OS.

There is **no tool-use loop, no multi-step agent, no orchestration framework** in the product. Planned-but-unbuilt LLM applications: mission planning and the "integration copilot" that reads the HAL registry — the registry law exists to feed it.

## §14 · RL, simulation, Isaac, learning pipelines

**None implemented, and none concretely planned in the repo.** `sim/` is a *protocol-and-behavior* fixture (a Python process speaking real LINK with fake movement and scripted sightings, indistinguishable from a real asset by message inspection), not a physics simulator. No Isaac Sim, no Gazebo, no training loop, no data pipeline, no fine-tuning story — the detector plan is off-the-shelf RF-DETR weights via TensorRT. The closest thing to sim-in-the-loop is the containerized Nav2 CI. The plan's "moat is the accumulated world model" implies a future data flywheel, but nothing collects training data today (no rosbag/MCAP recording exists).

One recorded sim-fidelity bug matters architecturally: `SimulatedLocomotion` models reverse while the real vehicle's reverse capability is *unverified* — the pre-survey notes said the protocol had none; the newer (still unverified) relay map lists R4 = reverse. Either way the simulator's capabilities are currently asserted rather than derived from ground truth, i.e. potentially easier to satisfy than the machine. `NEXT-STEPS.md` §3.2 proposes deriving sim capabilities from the manifest to close this.

## §15 · Main architectural assumptions baked in

1. **A frozen contract with open escape hatches is enough.** LINK v1 never reopens; everything new travels as open vocabulary (`task_type`), open structs (`Telemetry.payload`, `TaskParameters.extras`), or convention (cancel = TASK with status CANCELLED; registry rides telemetry).
2. **Single station, single server.** One TRACK process, SQLite single-writer, fusion centralized. Multi-station federation explicitly post-v1.
3. **MQTT-style eventual delivery** is the only transport property anything may assume.
4. **Localization is the locomotion driver's problem** (`pose()` on that interface), and a local tangent plane fixed at boot is accurate enough for any single task.
5. **Nearest-neighbor fusion with fixed gates is adequate at v1 scale**, behind a swappable Associator.
6. **Heartbeat cadence defines liveness** (5 missed = offline), measured by receipt time, not asset clocks.
7. **Perception can be reduced to Detections at the HAL boundary** — the runtime never sees pixels or points (see Risks).
8. **ROS 2 is containerizable and optional**: the core imports the Navigator protocol, never ROS; a machine can boot with no ROS at all.
9. **Token-file identity with two roles** is enough for now, as long as the enforcement point exists on every interface from day one.
10. **The operator surface is words**: every human-visible sentence lives in YAML data, per-deployment replaceable.

## §16 · Coupling, duplication, and hard-coding

- **Two vehicle stacks.** PILOT (HAL, LINK, manifests) and the teleop bridge (`VehicleAdapter`, its own JSON contract, its own watchdog, its own mock) are parallel systems that will both claim the same serial port on the same vehicle. `NEXT-STEPS.md` §3.5 proposes teleop as a C2 capability without porting the code, but nothing is built; the merge cost grows with every commit to either side.
- **Duplicated task/LINK logic.** `sim/vehicle.py` and `pilot/` each implement the five messages and the task state machine (two implementations of one contract is deliberate), but the sim duplicates *behavioral* logic that can drift from manifest truth — the reverse-modeling bug is the proof.
- **The brain exists twice** (archived repo and monorepo, already diverging), calls Anthropic directly, and hardcodes a model name — the one live violation of the gateway law.
- **Shadow schema in open structs.** The registry snapshot (`Telemetry.payload["registry"]`), planned standing orders, and lap counts all travel as unversioned dict conventions. Individually recorded as open decisions; collectively a second, informal contract.
- **Localization hides in locomotion.** When GNSS + IMU + VSLAM fusion arrives, `LocomotionDriver.pose()` becomes the wrong seam — a localization provider is not a motor controller.
- **Nav2 parameter pushing is brittle.** Runtime `set_parameters` RPCs may be silently refused (logged, not fatal), leaving a machine navigating on another body's defaults; also `Nav2Navigator._length()` reaches into `bridge._locomotion`, a private crossing of its own seam.
- **Scaling shortcuts in TRACK.** Association scans all live tracks per observation from SQLite; `investigate_open_contacts` lists up to 10,000 tracks; track history lives inside the protobuf blob (200 points). Fine for a demo site, not for a dense theater.
- **ETA and progress derive from manifest max speed**, not measured speed — cosmetic today, misleading under real terrain.
- **Assorted:** ports 8090/8100/8200/8300/8099 as scattered defaults; the legacy host-side programs on the Jetson hardcode the old CH340 by-id serial path the survey already invalidated (the vehicle's adapter is now FTDI — `MCU-PROTOCOL.md`); the bridge daemon has zero logging; C2 stores its token in localStorage; a WebRTC video path is documented but nonexistent.

## §17 · Next 5–10 development steps, as the repo implies them

1. **Send the Stereolabs email** (air-gapped ZED licensing + ZED X support matrix on JetPack 6 / L4T 36.5). Drafted in `NEXT-STEPS.md`, marked unsent on the critical path.
2. **Bench-verify the relay map and flash the v4 watchdog firmware** — wheels off the ground, one relay at a time, starting with "R5 is neutral" because any failsafe builds on it. The highest-value safety work in the program.
3. **Write the real locomotion driver + truthful `ugv-01` manifest** from the verified map (bang-bang steering, firmware throttle counts, reverse only if R4 verifies, unverified fields marked), and make the sim derive its capabilities from the manifest.
4. **Resolve bang-bang steering vs Nav2 MPPI** — pulsed-relay driver, proportional firmware change, or a different controller. The first real test of whether the HAL holds.
5. **Run PILOT on the Jetson at all.** First boot, the containerized runtime against the mock, then the real adapter with the wheels up.
6. **ZED X sensor driver + RF-DETR/TensorRT perception** behind the SensorDriver interface — which immediately exposes the Detection-only interface question and forces the CUDA-in-container decision.
7. **Settle localization** (cuVSLAM vs ZED-native) on the bench, and decide whether `pose()` stays on the locomotion interface or localization becomes its own driver kind.
8. **Reconcile teleop with the architecture**: teleop as a first-class C2/OS capability, one wire contract, one watchdog story, bridge logging added before any incident needs reconstructing.
9. **Choose and license-verify a local LLM** and run the deployed profile end-to-end once, so the air-gapped story stops being unproven.
10. **Founder gates:** Gate-2 review of the running C2, then the approved Stage 5 remainder (brand pass, event-language pass, offline bundle, 15-minute demo script).

## §18 · Uncertainties about the intended vision

- **What the near-term demo actually is.** The plan's Stage 3B demo is an autonomous patrol with live detection; the survey concluded manual teleop is the honest demo (no sensors on the vehicle). Which one the next quarter builds toward changes the priority of everything in §17.
- **Where the "Soul"/brain lives** — Jetson-side (the June Argus_Drive design) vs platform-side in TRACK (what got built). `NEXT-STEPS.md` recommends TRACK for v1; unresolved by the founder.
- **Whether ROS 2 is load-bearing or optional long-term.** Nav2 is its only consumer; DirectNavigator is what actually runs everywhere outside the container. If MPPI loses the bang-bang steering fight, the case for carrying ROS 2 at all should be re-argued rather than inherited.
- **Fleet scale ambitions** — SQLite + nearest-neighbor + single station are right for one site and a handful of assets; Lattice-class ambition implies federation, mesh comms, and probabilistic tracking that nothing yet sketches.
- **The teleop product question** — is manual driving a mode of the OS (one contract) or a separate Drive product (two)? Decision 4 settled the naming; the code still embodies two systems.
- **Commercial posture of LINK** — "open interface, closed core" is stated; no partner-facing artifact beyond `link/README.md` exists yet, and the product name is still a placeholder threaded through topic prefixes.

---

## Appendix A · System diagram, as built

```
            OPERATOR LAPTOP / GROUND STATION                VEHICLE (Jetson — has never run PILOT/the OS)
 ┌───────────────────────────────────────────────┐      ┌──────────────────────────────────────────────┐
 │  C2 (React/Leaflet)      voice/ (FastAPI)     │      │  PILOT  python -m pilot.main                 │
 │  map · tasking · modes   PTT · readback       │      │  ┌─────────────────────────────────────┐     │
 │      │ REST/WS               │ REST (op token)│      │  │ AutonomyCore (one loop)             │     │
 │      ▼                       ▼                │      │  │  orders · sense · report · battery  │     │
 │  ┌─────────────────────────────────────┐      │      │  │        │                            │     │
 │  │ TRACK  world model (FastAPI)        │      │      │  │        ▼                            │     │
 │  │  ingest → fusion → tracks/events    │      │      │  │ Navigator (protocol)                │     │
 │  │  zones · autonomy · watchdog        │      │      │  │  Direct ──────── Nav2 (ROS2 ctr)    │     │
 │  │  SQLite ▪ Redis(opt) ▪ tokens.yaml  │      │      │  │                   │ cmd_vel/odom    │     │
 │  └──────────────┬──────────────────────┘      │      │  │            LocomotionBridge         │     │
 │                 │ MQTT ▪ protobuf (LINK v1)   │      │  ├─────────── HAL seam ────────────────┤     │
 │   HEARTBEAT · TELEMETRY · OBSERVATION ·       │◄────►│  │ Locomotion │ Sensor │ Comms drivers │     │
 │   TASK_STATUS   ▲            TASK ▼           │      │  │ (simulated / mqtt today; zed_x,     │     │
 │                 │                             │      │  │  motor ctrl, GNSS = Stage 3B)       │     │
 │  ┌──────────────┴───────────┐                 │      │  └──────────────┬──────────────────────┘     │
 │  │ sim/  simulated vehicle  │ (CI fixture)    │      │   manifest.yaml │ registry :8200             │
 │  └──────────────────────────┘                 │      └─────────────────┼────────────────────────────┘
 │                                               │                        ▼  (future serial driver)
 │  gateway/  AI GATEWAY (library, in-process)   │      ┌──────────────────────────────────────────────┐
 │   capability → adapter, policy profiles       │      │  MCU (Arduino): R1..R14 relays, P42..214 PWM │
 │   whisper ▪ piper ▪ anthropic(dev) ▪ llama(✗) │      │  map UNVERIFIED · v4 watchdog fw not flashed │
 └───────────────────────────────────────────────┘      └──────────────────────────────────────────────┘

  PARALLEL TELEOP STACK (own JSON contract, not LINK)
  cockpit (browser) ──ws──► bridge daemon ──► VehicleAdapter (mock) ··► [real MCU adapter: not built]
        gamepad/keys        auth · watchdog        └─ LinkReporter (optional) ──MQTT──► TRACK
                            STOPPED/DRIVING/LATCHED
```

## Appendix B · Directory map → architectural component

```
Argus_OS/
├─ ARGUS-OS-PLAN.md        the constitution's constitution: laws, ontology, stages, open decisions
├─ STATUS.md               one line per system node, kept current
├─ NEXT-STEPS.md           staged proposal (4 Aug): critical path = Stereolabs + MCU firmware
├─ link/                   THE CONTRACT — protos (ontology.proto, messages.proto), buf config,
│  └─ gen/{python,ts}      generated bindings; pip-installable `link-contract`; zero repo imports
├─ track/                  THE WORLD MODEL — worldmodel.py (ingest/tasking/autonomy/watchdog),
│                          fusion.py (Associator), store.py (SQLite), live.py (Redis bus),
│                          api.py (REST+WS), identity.py (tokens), zones/events/data yaml
├─ c2/                     OPERATOR APP — React/Vite/Leaflet; sdk/ (the only TRACK access),
│                          state/world.ts, ui/ (Shell, Operate, MapView, VoiceBar), map/terrain.ts
├─ gateway/                AI GATEWAY — capabilities.py, policy.py (profiles), service.py,
│                          adapters/ (anthropic_cloud, llama_local, speech_local)  ← only place
│                          in the repo allowed to name a model or provider (tested)
├─ voice/                  VOICE SERVICE — service.py (readback state machine), intent.py
│                          (schema + validation vs world), world.py (HTTP client), characters/*.yaml
├─ drive/                  THE VEHICLE-SIDE PRODUCT (ARGUS DRIVE)
│  ├─ pilot/               EDGE RUNTIME — main.py, runtime.py, link_client.py,
│  │  ├─ autonomy/         core.py, navigator.py, nav2.py, worldslice.py
│  │  ├─ hal/              interfaces.py, manifest.py, registry.py, loader.py,
│  │  │  └─ drivers/       simulated.py, mqtt.py            ← the whole HAL
│  │  ├─ manifests/        ugv-reference.yaml, ugv-light.yaml
│  │  ├─ ros/              bridge.py (cmd_vel/odom/TF), nav2 config+launch, container tests
│  │  └─ docker/           ros:humble container (no CUDA/TensorRT)
│  ├─ bridge/              TELEOP DAEMON — daemon.py, watchdog.py, vehicle.py (mock),
│  │                       contract.py (own JSON wire), link_reporter.py (optional LINK feed)
│  ├─ cockpit/             TELEOP UI — React; input/ (gamepad), transport/, brain/ client
│  └─ brain/               LLM PROTOTYPE — Node, direct Anthropic SDK (law violation, flagged)
├─ bodies/ugv-01/          HARDWARE TRUTH — FINDINGS.md (survey), MCU-PROTOCOL.md (unverified map),
│                          firmware/ (original + v4 watchdog sketch, unflashed)
├─ sim/                    SIMULATED VEHICLE — permanent CI fixture speaking real LINK
├─ tests/                  full in-process loop: sim+TRACK+C2 contract+pilot+voice+gateway laws
└─ scripts/                preflight.sh, verify_install.py (deployment prover), verify_link.py
```

## Appendix C · Technology inventory

| Layer | In use | Chosen, not yet integrated |
|---|---|---|
| Contract | Protobuf 5, buf (lint + breaking-change CI), ULIDs, WGS84 | — |
| World model | Python 3.12–3.14, FastAPI, uvicorn, SQLite, redis-py, paho-mqtt, PyYAML | — |
| Messaging | Mosquitto (MQTT), WebSocket (FastAPI) | mesh radio, satellite (comms drivers) |
| Edge runtime | ROS 2 Humble, Nav2 (MPPI) + nav2_simple_commander, rclpy, tf2_ros, Docker | rosbag2/MCAP, Foxglove |
| Perception | (simulated only) | ZED SDK / ZED X (GMSL2), RF-DETR Apache tiers, TensorRT, cuVSLAM-or-ZED localization |
| AI | whisper.cpp (ggml-base.en), Piper (libritts_r voice), Anthropic SDK (dev/demo only) | local LLM: unchosen, unlicensed, unproven |
| Operator app | React 18, Vite 5, Leaflet 1.9, vitest; procedural local map tiles | WebRTC video (documented, absent) |
| Hardware | Jetson AGX Orin 64GB (JetPack 6.2 / L4T 36.5), Arduino-class MCU, FTDI serial | ZED X camera, GNSS, IMU (none attached) |
| Licensing | `LICENSES.md` tracks every direct dependency with military-use verdicts; AGPL and Chinese-origin models excluded by law; ZED SDK and NVIDIA redistribution terms flagged unverified | |

## Appendix D · Architectural risks / potential wrong direction

First, the fair frame: for a system whose stated goal is a modular, edge-first autonomous OS, the load-bearing choices — a frozen separable contract, a tested HAL with manifests, capability-gated AI, disconnection as a law with CI proof — are the *right* ones and are genuinely enforced. The risks below are where the current code could still prevent that goal.

**1 · The HAL abstracts detections, not sensing (highest architectural risk).** The implemented sensor interface is `poll() → list[Detection]`: class, confidence, offset. No images, no depth, no point clouds, no IMU/GNSS samples cross the HAL. That means (a) the detector must live *inside* each camera driver — so swapping RF-DETR for something else is a driver rewrite per sensor, weakening the "perception is swappable" story the sovereignty pitch depends on; (b) Nav2's costmaps can never receive obstacle data through the current seams, so real obstacle avoidance has no path; (c) localization fusion has no inputs. The plan promised standardized raw outputs; the code narrowed it. Cheap to fix now (a second, richer sensor-stream interface next to `poll()`) and expensive after three real drivers exist.

**2 · Localization is welded to locomotion.** `pose()` on the locomotion driver means "where am I" is answered by the thing that turns wheels. Works for dead reckoning and maybe for ZED-native, but a GNSS+IMU+VSLAM fusion has no home, and the open cuVSLAM-vs-ZED decision will be distorted by which option fits the existing seam rather than which is better. A fourth driver kind (localization) is the honest shape.

**3 · Two parallel vehicle stacks are accreting independently.** PILOT and the teleop bridge each have a vehicle abstraction, a wire contract, a watchdog, and a mock — and manual teleop just became the demo path, so the *non-architectural* stack is the one getting hardware attention. Left alone, the real MCU adapter gets written twice against an unverified relay map, and the safety stories diverge exactly where they must not. Decide now that the bridge's adapter is a thin shim over the HAL driver, or accept a planned merge cost.

**4 · The frozen contract is growing a shadow contract.** Registry-in-telemetry, cancel-as-status, laps-in-extras, standing-orders-to-come: each is a reasonable use of the schema's open extension points, and each is an unversioned dict convention a partner integrating against LINK cannot discover from the protos. The moat is supposed to be the contract; conventions that live in Python docstrings are not contract. A versioned conventions registry (or promoting stable conventions into v2) keeps the open-interface strategy honest.

**5 · Near-zero hardware contact, and the first contact is hostile.** PILOT and the OS runtime have never run on a Jetson (only the stdlib bridge relay has, briefly and successfully); the container base has no CUDA/TensorRT; the installed ZED SDK's drivers don't match the flashed kernel; the camera stack pierces the container boundary (GMSL2 depends on host BSP), so containerization does not de-risk the host question. Meanwhile the vehicle's firmware latches throttle on link loss and its steering can drive itself into a mechanical stop. The architecture is provably clean above the drivers, but "3B is just drivers and a manifest" is an untested claim, and the MPPI-vs-bang-bang problem is already a known case where the machine reaches above the HAL. Budget for the HAL being wrong once.

**6 · The air-gapped intelligence path is a paper capability.** The sovereignty differentiator — "no cloud in mission paths" — currently rests on an adapter that has never answered a request, with no model chosen and none license-cleared. Every voice feature was built and tuned against Claude. The risk isn't that local inference won't work; it's that intent quality, latency, and JSON-schema discipline were all validated against a frontier model, and the deployed profile may need real prompt/schema rework on a 7B-class model. Prove it early, before it becomes a demo-week discovery.

**7 · Single-station centralization vs the fleet pitch.** All fusion, all identity resolution, all autonomy policy live in one TRACK with SQLite and full-table association scans. Fine for v1's one site; but "machines behave as one force" at Lattice scale implies multi-station, asset-to-asset relay, and probabilistic tracking — none of which the current storage or association design anticipates beyond the Associator seam. The provisional-identity convention (asset ULIDs indistinguishable from resolved ones on the wire) is the first thing that breaks under federation.

**8 · Teleop security is far below the rest of the system's discipline.** The relay (`argus_relay.py`) exposes live drive control to the public internet via Tailscale Funnel, gated by a single static shared password sent as the first frame; the bridge daemon uses the same one-password model with no per-operator identity, no rate limiting, and **zero logging** — no session can be reconstructed after an incident; C2 keeps its bearer token in localStorage. TRACK's token-and-roles boundary was built early precisely because permission boundaries can't be retrofitted — the teleop path skipped that lesson, and it is now the demo path for a defence product driven over the internet.

**9 · Process risk: the founder is the pipeline.** Stage gates, frontend gates, open-decision resolution, and model escalation all serialize through one person, and the repo's own critical-path table shows the two items blocking everything (Stereolabs email, MCU firmware verification) sat idle while gated software work completed. The architecture is disciplined; the discipline currently costs calendar time exactly where hardware lead times are longest.

---

*Audit generated read-only from source; no code was modified. Independently reviewed against the code by a second model (Fable 5), 2026-08-17.*
