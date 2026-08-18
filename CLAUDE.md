# ARGUS OS: repository memory

## Rule zero: are you running on a vehicle?
If this checkout is on a Jetson inside a body (ugv-01 or any other steel), you
are on a machine that can move, and that outranks every command below.

- Run NOTHING that could actuate: no writes to serial ports, no motor tests,
  no `drive.bridge` against a real adapter, no `pilot.main` with real
  locomotion drivers, unless the human confirms the wheels are off the ground
  and says go. Opening a serial port even read-only can reset an MCU.
- Do NOT follow the install or dev commands in this file or in INSTALL.md by
  default. They assume a laptop. On a vehicle, read `bodies/<body-id>/SURVEY.md`
  first and do only what it says.
- The mock bridge (`python3 -m drive.bridge`, mock is the only adapter that
  exists) never touches a serial port and is safe. Anything else that reaches
  hardware is not, yet.
- The hardware safety gate in ARCHITECTURE.md section 6 is absolute: no
  autonomous moving test before the MCU fail-safe path is bench-proven.

## Source of truth (reorganized 18 Aug 2026, founder instruction, D-12)
- **ARCHITECTURE.md** is the canonical target architecture and holds the
  eighteen laws. Read it before any architectural change. Full depth:
  `ARGUS_ARCHITECTURE_ALIGNMENT_REPORT.md`.
- **The Engineering Knowledge Graph** (`docs/architecture/graph/`) and the
  generated **STATUS.md** are the truth about what exists and how mature it
  is. Read them before claiming something exists; query
  `.venv/bin/python scripts/argus_graph.py impact <id>` before large changes.
- **ADRs** (`docs/architecture/decisions/`) explain every frozen boundary. Read
  the relevant ADR before touching one; changing it means writing a
  superseding ADR, never a silent edit.
- **NEXT-STEPS.md** is the prioritized roadmap. **PROJECT.md** is product
  context. **ARGUS-OS-PLAN.md is historical**: it records the v1 stages and
  founder decisions of the plan era; where it conflicts with ARCHITECTURE.md,
  ARCHITECTURE.md wins. Decisions now live in
  `docs/architecture/graph/decisions.yaml`.
- Where any document conflicts with the code on what exists, the code wins.
  Where code conflicts with ARCHITECTURE.md on direction, that is a tracked
  gap, not a license.

## The laws
Eighteen, full text in ARCHITECTURE.md section 2; enforcement map in
`docs/architecture/graph/laws.yaml`. The short form of what they forbid you:

- Nothing hardware-specific above the HAL; nothing model-specific outside the
  gateway; applications use public interfaces only.
- No cloud in mission paths; air-gapped targets; no Chinese-origin models in
  deployed profiles (check the backbone, not the badge); licenses verified
  before integration (LICENSES.md).
- Operators see a map, plain sentences, and voice; every operator-facing
  string is data; never claim unearned certainty; unknown enum values pass
  through, never dropped.
- Models propose typed plans; they never command actuators. No silent
  self-modification in the field. SSH fixes return to Git.
- Every machine keeps persistent local truth; provenance is never lost.
- "Built" has evidence levels; promoting maturity without evidence is a lie
  CI rejects. The graph must stay consistent with the repo, same commit.

## Working rules
- Founder gates are real: stages and frontend surfaces need explicit approval
  (gate history in ARGUS-OS-PLAN.md sections 5 and 9). Open decisions
  (`decisions.yaml`, status open) are flagged and asked, never resolved
  silently. New uncertainty becomes a decisions.yaml entry, not a guess.
- After any substantive code change, run the law-auditor agent before
  presenting work.
- Update `docs/architecture/graph/*.yaml` and regenerate STATUS.md
  (`.venv/bin/python scripts/argus_graph.py status --write`) in the same
  commit as any change to a component's state. CI fails on drift.
- The simulated vehicle's full task loop must pass before any commit to
  TRACK or link/. The edge runtime's five criteria must pass before any
  commit to drive/pilot/ or track/.
- Voice executes nothing without a readback confirmation. No exceptions.
- Model escalation protocol (ARGUS-OS-PLAN.md section 11): after two failed
  serious attempts, stop and recommend a model switch.
- No emdashes in any prose or documentation. Plain, direct language.
- Do not reorganize directories to match the target layout; that is open
  decision OD-17, proposed per slice, never performed blindly.

## Layout (grows as built)
- ARCHITECTURE.md, PROJECT.md, RESEARCH.md, STATUS.md (generated), NEXT-STEPS.md at root.
- architecture/: decisions/ (ADRs) and graph/ (the Engineering Knowledge Graph).
- link/: ontology + message protos, frozen at v1. Cleanly separable; no imports from anything else in this repo.
- track/: world model server (FastAPI, Redis, SQLite).
- drive/: the vehicle-side product. drive/pilot/ is the edge runtime (ROS2), with HAL under drive/pilot/hal/. Runs containerized; ROS2 Humble has no native macOS path. Machine differences live in drive/pilot/manifests/*.yaml and behind the driver interfaces, never above them.
- drive/cockpit/: teleop driving UI (operator laptop). drive/bridge/: the vehicle daemon (WebSocket + watchdog; test bridge and mock today; converging onto the HAL per ADR-0009). drive/brain/: archived LLM prototype, reference only, do not extend.
- bodies/: per-body hardware truth (MCU protocol, wiring, firmware, survey). bodies/ugv-01/ is the first steel.
- c2/: operator application (React, Vite, Leaflet).
- sim/: simulated vehicle. Permanent test fixture; runs in CI.
- gateway/: the AI gateway. The ONLY package allowed to name a model or a provider (law 3). Adapters under gateway/adapters/; policy profiles in gateway/data/policy_profiles.yaml. `deployed` refuses cloud, enforced at the point of use and covered by a test.
- voice/: the voice service. Character sheets are data (voice/characters/*.yaml). Reaches TRACK over its public HTTP interface with the operator's own token, never by importing it.

## Installing this on another machine
If the task is to install ARGUS on the machine you are running on, rather than
to develop it, **read INSTALL.md and follow it.** Do not improvise an install
from this file. Bracket the work with the two scripts:
`bash scripts/preflight.sh` before anything,
`.venv/bin/python scripts/verify_install.py` at the end (`pytest` proves the
code, not the deployment; it never opens a socket).

The container base image (`ros:humble-ros-base`) carries no CUDA and no
TensorRT, which is right for simulated perception and wrong for real sensors.
PILOT has never run on the Jetson; only the bridge relay has (see STATUS.md
hardware evidence).

## Commands
Prerequisites: buf, protoc, node/npm, python3 (all on PATH). One-time setup:
`cd link && npm install` and `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e link/` at repo root.

- Lint protos: `cd link && buf lint`
- Regenerate bindings (cleans gen/ first): `cd link && buf generate`
- Typecheck TypeScript bindings: `cd link && npm run typecheck`
- Verify Python bindings: `.venv/bin/python scripts/verify_link.py` (repo root)
- Breaking-change check: `cd link && buf breaking --against '../.git#tag=link-v1,subdir=link'`
- Run all tests (sim loop, pilot criteria, voice, laws, graph; no broker, ~12s): `.venv/bin/python -m pytest -q`
- Engineering graph: `.venv/bin/python scripts/argus_graph.py validate | status --write | incomplete | blockers | component <id> | impact <id> | decisions --open | risks`
- Operator app tests: `cd c2 && npm test` (plus typecheck and build)
- Start the brokers: `redis-server --daemonize yes && mosquitto -d`
- Run the world model server: `DB_PATH=var/track.db TOKENS_PATH=var/tokens.yaml PORT=8100 .venv/bin/python -m track.main`
- Run a simulated vehicle against it: `.venv/bin/python -m sim.main`
- Health check: `curl -s localhost:8100/health`

Port note: 8100, because something else on this machine occupies 8000.

### The AI gateway and voice
Requires the local speech stack: `brew install whisper-cpp ffmpeg`,
`.venv/bin/pip install piper-tts`, then the two models into `var/models/`
(INSTALL.md 2.6). **Use the `en_US-libritts_r-medium` voice** (the common
`lessac` voice is research-only; law 9).

- Capabilities check: `ARGUS_AI_PROFILE=dev .venv/bin/python -c "from gateway import Gateway; import json; print(json.dumps(Gateway().check(), indent=2))"`
- Run voice: `ARGUS_AI_PROFILE=dev TRACK_URL=http://127.0.0.1:8100 VOICE_PORT=8300 .venv/bin/python -m voice.main`
- Talk without a microphone: `curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"text":"what is happening"}' localhost:8300/v1/voice/say`

Profiles: `deployed` (default, air-gapped, refuses cloud), `dev` and `demo`
(cloud permitted). A misspelled profile is refused rather than defaulted.
`dev`/`demo` need `ANTHROPIC_API_KEY` (via `requirements-bench.txt`;
deliberately not in the base install). `deployed` needs `ARGUS_LOCAL_LLM`
**and** `ARGUS_LOCAL_MODEL` naming a model recorded in LICENSES.md; refusing
without it is the licensing law working, not a fault. Known gap: the local
language adapter has never answered a request (risk R-6).

### The edge runtime (PILOT)
- Five Stage 3A criteria (part of `pytest -q`): `.venv/bin/python -m pytest tests/test_pilot_loop.py -v`
- Run one machine, no ROS2: `.venv/bin/python -m pilot.main --manifest drive/pilot/manifests/ugv-reference.yaml`
- Query a running machine: `curl -s localhost:8200/registry` (also `/registry/drivers`, `/devices`, `/health`, `/configuration`)
- Mirrored through the contract: `curl -s -H "Authorization: Bearer $TOKEN" localhost:8100/v1/assets/<id>/registry`

Container (needs Docker; ROS2 Humble has no native macOS path):
- Build: `docker build -f drive/pilot/docker/Dockerfile -t argus-pilot:dev .`
- Bridge and Nav2 route tests (~50s): `docker run --rm -e ROS_DOMAIN_ID=42 argus-pilot:dev bash /opt/argus/pilot/docker/run_nav2_tests.sh pilot/ros/tests -q`
- Nav2 plus a machine driving through it: `docker compose -f drive/pilot/docker/compose.yaml up nav2 pilot`
- Diagnosis: `python3 drive/pilot/docker/diagnose_nav2.py` inside the container, with Nav2 up.

Two traps worth not rediscovering. Nav2's costmaps will not activate until
the locomotion bridge is publishing `base_link` against `odom`, so anything
that waits for Nav2 before starting the machine deadlocks. And `rclpy` is
initialised once per session in `drive/pilot/ros/tests/conftest.py`: a module
that shuts it down leaves the next module unable to bring it back, and the
symptom looks like a Nav2 fault.
