# ARGUS - build status

Generated from the Engineering Knowledge Graph. Do not edit by hand;
edit `docs/architecture/graph/*.yaml`, then run
`.venv/bin/python scripts/argus_graph.py status --write`.
CI fails if this file drifts from the graph.

Maturity (law 17): `planned` < `scaffolded` < `simulated` <
`software_verified` < `hardware_integrated` < `field_validated`.
`simulated` means proven only against simulated hardware or fixtures.
Nothing here has been field validated, and 4 components have hardware evidence (listed below).
Disposition is the 18 Aug 2026 reconciliation
verdict: keep / refactor / replace / archive / new.

## Platform (ground station and services)

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| ARGUS LINK (`platform.link`) | software_verified | keep | - |
| ARGUS TRACK (`platform.track`) | software_verified | keep | 2 known gaps |
| ARGUS C2 (`platform.c2`) | software_verified | keep | 5 known gaps |
| Design tokens (`platform.design`) | software_verified | keep | - |
| AI Gateway (`platform.gateway`) | software_verified | keep | 1 known gap |
| Voice service (`platform.voice`) | software_verified | keep | 1 known gap |
| Argus Sync (`platform.sync`) | planned | new | - |
| Teleop cockpit (`teleop.cockpit`) | software_verified | refactor | 2 known gaps |
| Simulated vehicle (`sim.vehicle`) | simulated | keep | - |

## Edge (the machine)

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| ARGUS PILOT (`edge.pilot`) | hardware_integrated | keep | BLOCKED (1); 2 known gaps |
| Hardware abstraction layer (`edge.hal`) | simulated | keep | - |
| ugv-01 vehicle driver (two boards) (`edge.hal.ugv01`) | hardware_integrated | keep | BLOCKED (2); 6 known gaps |
| SensorDriver interface (Detection-only) (`edge.hal.sensor_interface`) | simulated | replace | 1 known gap; succeeded by `core.perception_interface` |
| LocomotionDriver interface (`edge.hal.locomotion_interface`) | simulated | refactor | 1 known gap |
| CommsDriver interface (`edge.hal.comms_interface`) | software_verified | keep | - |
| MQTT comms driver (`edge.hal.mqtt_comms`) | software_verified | keep | - |
| Simulated driver set (`edge.hal.simulated_drivers`) | simulated | keep | 1 known gap |
| Autonomy core (`edge.autonomy_core`) | simulated | refactor | - |
| Navigator (Direct and Nav2) (`edge.navigator`) | simulated | keep | 3 known gaps |
| WorldSlice (`edge.worldslice`) | software_verified | keep | - |
| Edge LINK client (`edge.link_client`) | software_verified | keep | - |
| Teleop bridge daemon (`teleop.bridge`) | software_verified | refactor | 3 known gaps |
| Bridge relay (`teleop.relay`) | hardware_integrated | refactor | 1 known gap |
| Teleop watchdog (`teleop.watchdog`) | software_verified | keep | 1 known gap |
| Brain prototype (`drive.brain`) | scaffolded | archive | 1 known gap; succeeded by `core.cognitive_runtime` |
| ZED provider (`perception.zed`) | planned | new | BLOCKED (2); 1 known gap |
| Object detector (RF-DETR) (`perception.detector`) | planned | new | - |

## Core (the cognitive architecture, target)

| Component | Maturity | Disposition | Notes |
|---|---|---|---|
| Argus Cognitive Runtime (`core.cognitive_runtime`) | planned | new | - |
| Local World Model (`core.local_world_model`) | software_verified | new | 2 known gaps |
| Perception stream interfaces (`core.perception_interface`) | software_verified | new | 2 known gaps |
| LocalizationProvider (`core.localization_provider`) | software_verified | new | 1 known gap |
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
| ugv-01 hardware truth (`bodies.ugv01`) | scaffolded | keep | BLOCKED (2); 5 known gaps |
| Silence watchdogs for the two boards (AC 1.3, 4.1.5) (`bodies.ugv01.firmware_watchdog`) | hardware_integrated | keep | BLOCKED (1); 5 known gaps |
| v4 watchdog firmware (relay board, superseded) (`bodies.ugv01.firmware_v4`) | scaffolded | archive | BLOCKED (1); 1 known gap |

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
- `edge.hal.ugv01`: Bench run with the human at the key (bodies/ugv-01/FINDINGS-2026-10-13.md section 7 questions answered first); first power-up with propulsion inhibited and bounded brake pulses, per Codex checkpoint 2
- `edge.hal.ugv01`: Codex Astra checkpoint 2 (13 Oct 2026): the reproduced interlock bugs are fixed and regression-tested; the items listed under known_gaps stay open and are reviewed again before the first powered run
- `perception.zed`: An ARGUS perception provider over the ZED SDK, in the container, which has no CUDA today
- `perception.zed`: Air-gapped SDK activation and field licensing unverified with Stereolabs (decision D-2); PARKED on founder instruction 18 Aug 2026
- `bodies.ugv01`: Bench verification of the two new boards (bodies/ugv-01/FINDINGS-2026-10-13.md section 7), wheels off the ground, one command at a time, with pilot/hal/drivers/ugv01/bench.py
- `bodies.ugv01`: A proven stop on link loss on both boards (firmware watchdog or an independent stop) before any autonomous motion (ARCHITECTURE.md section 6)
- `bodies.ugv01.firmware_watchdog`: The section 6 gate stays shut until the stops are measured electrically (meter on the Nano's pin 9 and on the relay coils, README-WATCHDOG.md steps 2 and 4), brake and centring silence pass, refusal while latched and steps 3, 5, 6, 7 and 9 are exercised, and the undriven relay-input window is closed with pull-ups; Gulshan's observations for the steering run and the ignition windows are still owed
- `bodies.ugv01.firmware_v4`: The link-loss stop now has to be built or proven on the ARGUS DRIVE module and the accelerator board instead

## Hardware evidence (everything else is Mac and CI containers)

- `edge.pilot`: 2026-10-13: first boot on the Jetson AGX Orin in the vehicle, in the argus-pilot:dev container built on the Jetson (arm64, 173 s): simulated locomotion, dead-reckoning localization, simulated camera, MQTT comms to the laptop's broker over an SSH tunnel on Tailscale; registry served on the Jetson and read from the Mac; registered in TRACK as 01PILOT00000000000000UGV1 (STANDBY) with --prefix argus. No ROS2 in the path, no real driver. Logs: bodies/ugv-01/reference/2026-10-13/pilot_*.log.
- `edge.hal.ugv01`: 2026-10-13: bench on the vehicle, wheels on jacks, Gulshan Shah at the key, founder relaying. From ARGUS code on the Jetson: both boards identified (drive 4.1.4, accel 1.2), STATUS read, lights, indicators and horn acknowledged, gear D proven by STATUS, steering left and right with feedback (left increases the reading, about 67 deg/s), throttle 20 percent acknowledged and the wheels turned, brake applied and released with feedback (61.7 released end, about 100 deg/s). Partial bench integration: no braking force, no ground contact, no speed. Record: bodies/ugv-01/BENCH-RESULTS-2026-10-13.md, logs in bodies/ugv-01/bench-logs/2026-10-13/.
- `edge.hal.ugv01`: 2026-10-13, Phase E: throttle held at 20 percent, host silent 15.0 s with ports open and the board powered; the wheels turned (19 s by a human stopwatch) until the zero arrived. No stop on silence occurred in that window. Finite, powered, ports-open test; port close and reset not tested. The section 6 gate stays shut.
- `edge.hal.ugv01`: 2026-10-15: the same controls drove the watchdog runs on the vehicle (bodies/ugv-01/BENCH-RESULTS-2026-10-15.md): both boards' trip notices received and turned into faults, the host's fallback stop sent within a millisecond of the drive module's notice, clears only on command, no nuisance trip under the 250 ms keepalive, and the bench's room rule refused two steering steps correctly. Identity 4.1.4 then 4.1.5 on the drive module, AC 1.3 on the accelerator.
- `teleop.relay`: 2026-08: ran on the Jetson AGX Orin over a 271 ms relayed link, 30 s at 15 Hz, zero watchdog latches, no frame loss, 0.4 percent CPU (recorded in docs/architecture/audits/2026-08-17-as-built-audit.md section 3 and in pre-graph STATUS.md git history). Network path only; no vehicle actuation involved.
- `bodies.ugv01.firmware_watchdog`: 2026-10-15, evening IST: the silence watchdogs on the vehicle, drive wheels on a jack, Gulshan Shah at the jeep, the founder pasting each command (the harness refused the agent every port-opening command). Accelerator AC 1.3 silence twice: throttle 20 percent then 1500 ms of host silence, read-back shows duty at rest and the timeout count 0 to 1, then the throttle accepted again after the host's explicit zero (refusal while latched not exercised); Gulshan, on the second run: the wheel spun, stopped, spun again. 4.1.5 flashed onto the drive module from the Jetson (image c33a05ad..., key off), identity 040105 with WD=00. Drive module silence once: steer left then 900 ms of host silence, the board printed 0x00;WD;TIMEOUT 851 ms after its OK, steering stopped at 154.7 deg by the angle sensor, WD count 0 to 1, the next move accepted after the host's explicit stop (refusal while latched not exercised; Gulshan's words for this run not relayed). Then twenty cycles of throttle and steering under the 250 ms keepalive with no fault and no trip on either board; the steering watchdog tripped once more the other way (stop at 157.3 deg, WD 0 to 1). Two key cycles inside a listening window: no reset line, no flicker (Gulshan, relayed). The horn alone still corrupts both angle sensors and the host stops on it; a ten minute traffic attempt was stopped at 21 s by the host's single-miss angle rule when one steering poll read NO_SIGNAL as a relay switched off, with no trip from the board (wiring and host policy, not firmware). Record bodies/ugv-01/BENCH-RESULTS-2026-10-15.md, logs bodies/ugv-01/bench-logs/2026-10-15/. Not measured electrically; brake and centring silence untested; the gate stays shut.
- `bodies.ugv01.firmware_watchdog`: 2026-10-15: identity read from the Jetson over SSH (founder typed the command; bench_run_2026-10-14.py, steps snap, status, readback; log bodies/ugv-01/bench-logs/2026-10-15/bench_ugv01_2026-10-15_run0.jsonl). Drive module answers 4.1.4 (the team's rollback is real, STATUS has no WD field), throttle Nano answers AC 1.3 with read-back working and timeouts 0. Steering 161.4 deg, brake 61.7 deg (released end), gear D, Wi-Fi off, no faults, stop on close acknowledged. No motion commanded.
- `bodies.ugv01.firmware_watchdog`: 2026-10-15: all four images built on the Jetson (tessy, JetPack R36.5, aarch64) by build.sh with PlatformIO Core 6.2.0 (espressif32 7.1.3) and arduino-cli (arduino:avr 1.8.8): drive 4.1.4 81e45b6e..., drive 4.1.5 c33a05ad..., Nano AC 1.2 78f465a1..., Nano AC 1.3 da0f82b2... (full SHA-256 in bodies/ugv-01/firmware/BUILDS.md, log in bodies/ugv-01/bench-logs/2026-10-15/build-sh.log). Build only: no port opened, nothing flashed, nothing moved.

## Open decisions (founder-gated; details in docs/architecture/graph/decisions.yaml)

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
- OD-23: Approvals that go stale between preview and issuance

Roadmap and critical path: NEXT-STEPS.md. Target architecture: ARCHITECTURE.md.
