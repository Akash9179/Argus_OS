# ARGUS - build status

One line per system-map node. Same names as the visual map. Update in every
PR that changes a node's state. Legend: [x] built (CI green) · [~] in
progress · [!] blocked · [ ] planned.

## ARGUS OS
- [x] LINK - contract v1 frozen; Python + TypeScript bindings
- [x] TRACK - world model: ingest, fusion, registry, tasks, REST/WS
- [~] Core services
  - [x] AI Gateway - adapters + policy profiles (air-gapped LLM path UNPROVEN)
  - [x] Voice - push-to-talk, readback confirmation, all via gateway
  - [~] Identity + comms - operator tokens only; full stage post-S5
- [~] Applications
  - [x] C2 - map, tracks, tasking, voice console (Gate-2 review pending)
  - [~] Intel - exists as voice Q&A over world model
  - [ ] Plan / Review / Fleet - post-v1
- [~] ARGUS DRIVE
  - [~] PILOT - everything above drivers built + CI green (S3A); real drivers await hardware (S3B)
    - [x] Autonomy core · [x] Navigation (Nav2, sim drivers) · [x] HAL (3 interfaces, registry, manifests)
    - [!] Perception - ZED X; blocked on Stereolabs answers + steel
  - [~] Manual mode
    - [~] Cockpit - UI v0 + bridge-protocol transport (?bridge=host), ignition control, live vehicle telemetry in HUD. Pending: video pane
    - [x] Watchdog + self-test - ignition triggers pre-arm checks (green light gates arming); silence/link-loss latches stop, explicit re-arm (mock-tested; hardware validation pending)
    - [~] Bridge - daemon v1 + LINK reporter (--report): the driven vehicle registers in TRACK and moves on the Operate map, 20 tests. Pending: video, real ugv-01 adapter (post-survey)
  - [~] Brain - v0.1 prototype (direct SDK; must move behind gateway)

## Bodies
- [x] Sim vehicle - permanent CI fixture
- [~] ugv-01 - Jetson in hand; hardware upgraded, SURVEY PENDING (see bodies/ugv-01/)
- [ ] UAV / USV / cargo / fixed sensors

## Stages (plan §9)
S1 ✓ · S2 ✓ · S3A ✓ · S3B blocked (hardware) · S4 ✓ · S5 in progress

## Critical path (demo)
1. Stereolabs email (ZED X air-gap licensing + JetPack support) - UNSENT
2. Vehicle hardware survey → bodies/ugv-01/ checklist
3. Gate-2 review of C2 (~30 min)
4. Stage 5 remainder approval
