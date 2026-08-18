# ARGUS - build status

Generated from the Engineering Knowledge Graph. Do not edit by hand;
edit `architecture/graph/*.yaml`, then run
`.venv/bin/python scripts/argus_graph.py status --write`.
CI fails if this file drifts from the graph.

Maturity (law 17): `planned` < `scaffolded` < `simulated` <
`software_verified` < `hardware_integrated` < `field_validated`.
`simulated` means proven only against simulated hardware or fixtures.
Nothing here has been field validated, and 1 component has hardware evidence (listed below).
Disposition is the 18 Aug 2026 reconciliation
verdict: keep / refactor / replace / archive / new.

## Platform (ground station and services)

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| ARGUS LINK (`platform.link`) | software_verified | keep | 1 known gap |
| ARGUS TRACK (`platform.track`) | software_verified | keep | 2 known gaps |
| ARGUS C2 (`platform.c2`) | software_verified | keep | 3 known gaps |
| AI Gateway (`platform.gateway`) | software_verified | keep | 1 known gap |
| Voice service (`platform.voice`) | software_verified | keep | 1 known gap |
| Argus Sync (`platform.sync`) | planned | new | - |
| Teleop cockpit (`teleop.cockpit`) | software_verified | refactor | 1 known gap |
| Simulated vehicle (`sim.vehicle`) | simulated | keep | 1 known gap |

## Edge (the machine)

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| ARGUS PILOT (`edge.pilot`) | simulated | keep | BLOCKED (1); 1 known gap |
| Hardware abstraction layer (`edge.hal`) | simulated | keep | - |
| SensorDriver interface (Detection-only) (`edge.hal.sensor_interface`) | simulated | replace | 1 known gap; succeeded by `core.perception_interface` |
| LocomotionDriver interface (`edge.hal.locomotion_interface`) | simulated | refactor | 1 known gap |
| CommsDriver interface (`edge.hal.comms_interface`) | software_verified | keep | - |
| MQTT comms driver (`edge.hal.mqtt_comms`) | software_verified | keep | - |
| Simulated driver set (`edge.hal.simulated_drivers`) | simulated | keep | 1 known gap |
| Autonomy core (`edge.autonomy_core`) | simulated | refactor | - |
| Navigator (Direct and Nav2) (`edge.navigator`) | simulated | keep | 3 known gaps |
| WorldSlice (`edge.worldslice`) | simulated | replace | 1 known gap; succeeded by `core.local_world_model` |
| Edge LINK client (`edge.link_client`) | software_verified | keep | - |
| Teleop bridge daemon (`teleop.bridge`) | software_verified | refactor | 3 known gaps |
| Bridge relay (`teleop.relay`) | hardware_integrated | refactor | 1 known gap |
| Teleop watchdog (`teleop.watchdog`) | software_verified | keep | 1 known gap |
| Brain prototype (`drive.brain`) | scaffolded | archive | 1 known gap; succeeded by `core.cognitive_runtime` |
| ZED provider (`perception.zed`) | planned | new | BLOCKED (3) |
| Object detector (RF-DETR) (`perception.detector`) | planned | new | - |

## Core (the cognitive architecture, target)

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| Argus Cognitive Runtime (`core.cognitive_runtime`) | planned | new | - |
| Local World Model (`core.local_world_model`) | planned | new | - |
| Perception stream interfaces (`core.perception_interface`) | planned | new | - |
| LocalizationProvider (`core.localization_provider`) | planned | new | - |
| Memory manager (`core.memory`) | planned | new | - |
| ActionVerifier (`core.action_verifier`) | planned | new | - |
| Safety governor (`core.safety_governor`) | planned | new | - |
| Skill registry and executor (`core.skills`) | planned | new | - |

## Domain execution layers

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| ARGUS DRIVE (`domains.drive`) | simulated | refactor | - |
| ARGUS FLIGHT (`domains.flight`) | planned | new | - |
| ARGUS SEA (`domains.sea`) | planned | new | - |

## Hardware bodies

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| ugv-01 hardware truth (`bodies.ugv01`) | scaffolded | keep | BLOCKED (1); 2 known gaps |
| v4 watchdog firmware (`bodies.ugv01.firmware_v4`) | scaffolded | keep | BLOCKED (1); 1 known gap |

## Learning plane

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| Experience recording (`learning.experience`) | planned | new | - |
| Isaac simulation and RL (`learning.isaac`) | planned | new | - |

## Operations

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| Install and verification tooling (`ops.install`) | software_verified | keep | - |
| Fleet deployment (`ops.fleet_deployment`) | planned | new | - |

## Engineering

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| Engineering Knowledge Graph (`engineering.graph`) | software_verified | new | - |
| Fast in-process test suite (`engineering.test_suite`) | software_verified | keep | - |

## Blockers

- `edge.pilot`: First boot on the actual Jetson (phase 3)
- `perception.zed`: Installed ZED SDK 5.4.1 bundles ZED X GMSL drivers for L4T 35.x; flashed kernel is L4T 36.5; the matching SDK must be installed when the camera arrives
- `perception.zed`: Camera ORDERED 18 Aug 2026, delivery expected within days, WITH the ZED Link GMSL2 capture card and cable (founder-confirmed); hardware connection path complete on arrival, driver bring-up remains
- `perception.zed`: Air-gapped SDK activation and field licensing unverified with Stereolabs (decision D-2); PARKED on founder instruction 18 Aug 2026
- `bodies.ugv01`: Bench verification of the relay map, wheels off the ground, one relay at a time
- `bodies.ugv01.firmware_v4`: Bench verification is the hard safety gate; no autonomous moving test happens before it passes (ARCHITECTURE.md section 6)

## Hardware evidence (everything else is Mac and CI containers)

- `teleop.relay`: 2026-08: ran on the Jetson AGX Orin over a 271 ms relayed link, 30 s at 15 Hz, zero watchdog latches, no frame loss, 0.4 percent CPU (recorded in architecture/audits/2026-08-17-as-built-audit.md section 3 and in pre-graph STATUS.md git history). Network path only; no vehicle actuation involved.

## Open decisions (founder-gated; details in architecture/graph/decisions.yaml)

- D-1: Localization source of truth (cuVSLAM vs ZED-native vs fused)
- D-2: ZED SDK / TERRA air-gapped licensing
- D-3a: Does the sovereignty law bite a model's architecture or only its weights
- D-6: Altitude in fusion association
- OD-13: Bang-bang steering vs Nav2 MPPI
- OD-14: Cognitive Runtime process model and AutonomyCore split
- OD-15: Perception API shape
- OD-16: Local journal and store format
- OD-17: Repository reorganization scope
- OD-18: Containers vs host on the Jetson
- OD-19: Local reasoning model selection
- OD-21: Provisional identity on the wire

Roadmap and critical path: NEXT-STEPS.md. Target architecture: ARCHITECTURE.md.
