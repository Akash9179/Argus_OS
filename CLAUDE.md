# ARGUS OS: repository memory

## Source of truth
ARGUS-OS-PLAN.md is the single source of truth. Read it before any non-trivial work. Where anything conflicts with it, the plan wins. Amendments to the plan happen only on the founder's explicit instruction, never silently.

## The ten laws (full text in plan section 2; these bind every commit)
1. HAL law: no vehicle/sensor/device specifics above the HAL.
2. SDK honesty law: applications use only public service interfaces; no backdoors.
3. Gateway law: no model or provider names outside the AI gateway.
4. Schema law: ontology multi-domain from the first line; ground implemented first.
5. Waterline law: operators never see internals; map, plain sentences, voice only.
6. Disconnection law: every asset fully functional alone; link adds, never enables.
7. Honesty law: never claim more certainty than held; spoken output always printed.
8. Sovereignty laws: air-gapped targets; no Chinese models; no cloud in mission paths.
9. Licensing law: verify every third-party license for military use before integration.
10. Registry law: everything the HAL knows is queryable structured data.

## Working rules
- Stages are gated (plan section 9). Stop at each definition of done and present for review. Never start the next stage without founder approval.
- Open decisions (plan section 10): flag and ask; never resolve silently.
- Frontend: founder review gates apply (plan section 5). Propose, do not proceed.
- Model escalation protocol (plan section 11): after two failed serious attempts, stop and recommend a model switch; do not iterate further.
- After any substantive code change, run the law-auditor agent before presenting work.
- The simulated vehicle's full task loop must pass before any commit to TRACK or link/.
- The edge runtime's five Stage 3A criteria must pass before any commit to pilot/ or track/.
- Unknown enum values are preserved and passed through, never dropped.
- No emdashes in any prose or documentation. Plain, direct language.

## Layout (grows as built)
- link/: ontology + message protos. Cleanly separable; no imports from anything else in this repo.
- track/: world model server (FastAPI, Redis, SQLite).
- pilot/: edge runtime (ROS2). HAL under pilot/hal/. Runs containerized; ROS2 Humble has no native macOS path. Machine differences live in pilot/manifests/*.yaml and behind the three driver interfaces, never above them.
- c2/: operator application (React, Vite, Leaflet).
- sim/: simulated vehicle. Permanent test fixture; runs in CI.

## Commands
Prerequisites: buf, protoc, node/npm, python3 (all on PATH). One-time setup: `cd link && npm install` and `python3 -m venv .venv && .venv/bin/pip install protobuf` at repo root.

- Lint protos: `cd link && buf lint`
- Regenerate bindings (Python + TypeScript, cleans gen/ first): `cd link && buf generate`
- Typecheck TypeScript bindings: `cd link && npm run typecheck`
- Verify Python bindings (import, round-trip, open-enum passthrough): `.venv/bin/python scripts/verify_link.py` (run from repo root)
- Breaking-change check against the frozen contract (after the link-v1 tag exists): `cd link && buf breaking --against '../.git#tag=link-v1,subdir=link'`

Python setup (once): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e link/`

- Run all tests, including the sim's full task loop (no broker needed, ~5s): `.venv/bin/python -m pytest -q`
- Run only the CI gate: `.venv/bin/python -m pytest tests/test_sim_loop.py -v`
- Start the brokers: `redis-server --daemonize yes && mosquitto -d`
- Run the world model server: `DB_PATH=var/track.db TOKENS_PATH=var/tokens.yaml PORT=8100 .venv/bin/python -m track.main` (tokens are generated into TOKENS_PATH on first run)
- Run a simulated vehicle against it: `.venv/bin/python -m sim.main` (add `--duration 60`, `--asset-id`, `--latitude/--longitude` as needed)
- Health check: `curl -s localhost:8100/health`

Port note: 8100, because something else on this machine occupies 8000.

### The edge runtime (PILOT)
Two CI gates now: the fast in-process one above, and a containerized one that needs ROS2. Both must pass.

- Run the edge runtime's five Stage 3A criteria (part of `pytest -q`): `.venv/bin/python -m pytest tests/test_pilot_loop.py -v`
- Run one machine with no ROS2 in the path: `.venv/bin/python -m pilot.main --manifest pilot/manifests/ugv-reference.yaml`
- Ask a running machine what it is made of: `curl -s localhost:8200/registry` (also `/registry/drivers`, `/devices`, `/health`, `/configuration`)
- Ask the world model the same thing, mirrored through the contract: `curl -s -H "Authorization: Bearer $TOKEN" localhost:8100/v1/assets/<id>/registry`

Container (needs Docker running; ROS2 Humble has no supported native macOS path):
- Build: `docker build -f pilot/docker/Dockerfile -t argus-pilot:dev .`
- Bridge and Nav2 route tests (~50s): `docker run --rm -e ROS_DOMAIN_ID=42 argus-pilot:dev bash /opt/argus/pilot/docker/run_nav2_tests.sh pilot/ros/tests -q`
- Nav2 plus a machine driving through it: `docker compose -f pilot/docker/compose.yaml up nav2 pilot`
- When a machine will not arrive and you need to see why: `python3 pilot/docker/diagnose_nav2.py` inside the container, with Nav2 already up.

Two traps worth not rediscovering. Nav2's costmaps will not activate until the locomotion bridge is publishing `base_link` against `odom`, so anything that waits for Nav2 before starting the machine deadlocks. And `rclpy` is initialised once per session in `pilot/ros/tests/conftest.py`: a module that shuts it down leaves the next module unable to bring it back, and the symptom looks like a Nav2 fault.
