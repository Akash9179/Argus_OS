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
- Unknown enum values are preserved and passed through, never dropped.
- No emdashes in any prose or documentation. Plain, direct language.

## Layout (grows as built)
- link/: ontology + message protos. Cleanly separable; no imports from anything else in this repo.
- track/: world model server (FastAPI, Redis, SQLite).
- pilot/: edge runtime (ROS2). HAL under pilot/hal/.
- c2/: operator application (React, Vite, Leaflet).
- sim/: simulated vehicle. Permanent test fixture; runs in CI.

## Commands
Prerequisites: buf, protoc, node/npm, python3 (all on PATH). One-time setup: `cd link && npm install` and `python3 -m venv .venv && .venv/bin/pip install protobuf` at repo root.

- Lint protos: `cd link && buf lint`
- Regenerate bindings (Python + TypeScript, cleans gen/ first): `cd link && buf generate`
- Typecheck TypeScript bindings: `cd link && npm run typecheck`
- Verify Python bindings (import, round-trip, open-enum passthrough): `.venv/bin/python scripts/verify_link.py` (run from repo root)
- Breaking-change check against the frozen contract (after the link-v1 tag exists): `cd link && buf breaking --against '../.git#tag=link-v1,subdir=link'`

(Test, sim-loop, and server commands are added in Stage 2.)
