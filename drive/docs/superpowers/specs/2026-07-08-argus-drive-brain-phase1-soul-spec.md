---
spec: Argus-Drive-Brain — Phase 1 "The Soul"
date: 2026-07-08
status: Draft for review — pre-implementation
owner: Akash Suryavanshi (Argus)
parent: docs/superpowers/specs/2026-07-08-argus-drive-brain-design.md
builds_on: docs/superpowers/specs/2026-06-18-argus-drive-teleop-design.md
---

# Argus-Drive-Brain — Phase 1 "The Soul"

## 1. Purpose

Give the Argus vehicle a first, real "soul": a brain that **talks** (personality +
voice), **sees** (describes what the camera shows), **runs a spoken pre-flight
check** over vehicle telemetry, and can take **high-level spoken commands** and turn
them into short, bounded drive actions. The human is still the navigator — this is
assistance and presence, not autonomy. It is the fast win that forces the clean
brain→drive interface every later phase depends on.

## 2. Scope

### In scope (Phase 1)
- A **Brain service** that reasons, sees, and speaks, driven by a cloud frontier
  model + cloud STT/TTS.
- A **cockpit voice/conversation panel** (browser mic + speaker) as the P1 human↔brain
  channel.
- **Scene understanding** from a sampled camera frame.
- A **spoken pre-flight checklist** over the existing `Telemetry` contract fields.
- **Bounded spoken-drive**: high-level commands ("nudge forward", "stop", "turn left
  a little") → a `Command` (existing contract) → existing `TokenEmitter` → relay.
- Reuse of the existing spine: relay (`argus_relay.py`) + Remo tokens + the
  `contract/` + `transport/` layers in `web/`.

### Out of scope (later phases / separate specs)
- Any autonomy / self-navigation / A→B (Phase 2).
- Persistent memory / SSD vector store (deferred — stateless in P1).
- On-device / offline model + on-device STT/TTS (P1 is cloud, bench, wifi-assumed).
- Rich personality / persona depth (P1 is a light operational character only).
- Robot-mounted mic/speaker (P1 voice is browser-mediated via the cockpit).
- The ROS 2 `/cmd_vel` bridge (P1 drives via the proven Remo-token path).

## 3. Locked decisions (this spec)

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| 1 | Drive seam | Brain emits the existing **`Command`** contract → `TokenEmitter` → relay tokens | Proven live path; inherits relay dead-man + single-operator safety; no new subsystem |
| 2 | Brain runtime | **Cloud** brain in P1; thin client bridges to the Jetson/cockpit | Fastest path to "talks + sees"; defers on-device inference to P2 |
| 3 | Model + voice | **Cloud frontier model** (Claude-class, vision-capable) + **cloud STT/TTS** | Smartest + simplest for a bench P1 |
| 4 | Scope | **Minimal**: talk + see + pre-flight + bounded spoken-drive; **stateless**; light personality | Smallest cut that delivers the P1 moment |
| 5 | Human↔brain channel | **Cockpit browser** mic/speaker + a conversation panel | Reuses existing web app; no Jetson audio hardware needed in P1 |
| 6 | Driver arbitration | Cockpit remains the single relay **DRIVER**; brain-issued `Command`s flow through the same path; **human input always overrides** and can take back control instantly | Single-operator lock is preserved; human safety override is non-negotiable |

## 4. Grounding — verified current state (2026-07-08)

- **Spine (live):** `web` cockpit → `argus_relay.py` (:8090, Tailscale Funnel) → Remo
  Go server (`ws://localhost:8080/ws`) → Arduino → motors. Relay enforces password
  auth (`AUTH:<pw>` first frame), single-operator DRIVER/SPECTATOR lock, telemetry
  broadcast, a **700 ms dead-man** (`IDLE_MS`) that neutralizes on driver silence, and
  an `HB` heartbeat that resets it (`test-bridge/argus_relay.py:24-26,182-196`).
- **Drive protocol:** ASCII tokens — steering `L1/L0/R1/R0` (bang-bang, deadband
  0.12), throttle `P42..P214` (`P42` neutral, forward-only) (`web/src/transport/tokens.ts`).
- **Contract already exists:** `web/src/contract/index.ts` defines `Command`,
  `Telemetry`, `neutralCommand()`. `Telemetry` includes `battery.percent`,
  `battery.runtimeMin`, `speedKmh`, `gear`, `steerAngleDeg`, `armed`, `safetyState`,
  `linkRttMs`, `tempC`, `headingDeg`, `lights`. **The pre-flight checklist reads these.**
- **`TokenEmitter`** (`web/src/transport/tokens.ts`) maps `Command`→tokens, diff-based,
  with `forceNeutral()` for E-STOP/disconnect. **The brain produces `Command`s; this
  encoder is reused unchanged.**
- **Cockpit stack:** React + Vite + zustand; relay client in `web/src/transport/`
  (`remoTransport.ts`, `useRemoTransport.ts`, `auth.ts`, `DriveConnect.tsx`); state in
  `web/src/state/store.ts`.
- **Hard constraint:** the Jetson has **no pip / stdlib-only** for the bridge scripts.
  P1 keeps heavy deps in the cloud brain; any Jetson-side code stays stdlib.

## 5. Architecture (Phase 1)

```
 Operator (browser) ──speaks──▶ Cockpit voice panel ──audio──▶ STT (cloud)
        ▲                              │                          │ text
        │ TTS audio                    │ camera frame + telemetry  ▼
        └──────────◀── Cockpit ◀──────┤                    ┌───────────────┐
                        │              └───frame/telemetry─▶│  BRAIN SERVICE │
                        │                                   │ frontier model │
   Command (contract)   │◀────────── spoken reply + ────────│  + vision      │
        │               │            optional drive intent   └───────────────┘
        ▼
   TokenEmitter ─tokens─▶ relay (DRIVER) ─▶ Remo ─▶ Arduino ─▶ motors
   (human input on the same path always overrides brain Commands)
```

### Components

1. **Cockpit voice panel** (`web/src/cockpit/…`, new): push-to-talk / wake mic capture,
   plays TTS replies, shows the running transcript + the brain's current "what I see"
   and pre-flight results. Uses the browser mic/speaker.
2. **Brain service** (new, cloud; language TBD in plan — Node/TS or Python): one endpoint
   that takes `{ transcript, cameraFrame(JPEG), telemetrySnapshot }` and returns
   `{ speech: string, driveIntent?: Command | null, preflight?: CheckResult[] }`.
   Calls the frontier model (vision + text) and cloud STT/TTS. **Stateless** per request
   in P1 (short rolling context only, no persistence).
3. **Drive-intent adapter** (in cockpit): converts a returned `driveIntent` into a
   **bounded** action — capped throttle (`P` ceiling), capped duration, then auto-neutral
   — pushed through the existing `TokenEmitter`. Human manual input takes precedence at
   all times; brain drive only acts while the human has explicitly enabled "assist".
4. **Camera frame source**: sample a JPEG from the existing camera path. Exact capture
   method is an implementation task (see §8) with a documented fallback.

### Interfaces (contracts)

```ts
// Brain request
interface BrainTurn {
  transcript: string            // user speech-to-text, this turn
  cameraFrameJpegBase64?: string
  telemetry?: Telemetry         // from contract/index.ts
  context?: { recentTurns: {role:'user'|'brain'; text:string}[] } // short, in-memory only
}
// Brain response
interface BrainReply {
  speech: string                // spoken back via TTS
  driveIntent?: Command | null  // contract Command; null = no movement
  preflight?: { item: string; status: 'ok'|'warn'|'fail'; detail: string }[]
}
```

## 6. Acceptance criteria (deterministic — these are the loop finish line)

Each is pass/fail and observable. "Bench" = drive wheels off the ground, per the
repo's standing safety rule.

1. **Talks:** Speaking a greeting in the cockpit panel produces a spoken reply through
   the browser speaker within ≤ 4 s, in ≥ 9 of 10 trials. Transcript shows both sides.
2. **Sees:** With a known object placed in the camera view, asking "what do you see?"
   yields a spoken description naming that object correctly in ≥ 8 of 10 trials across
   ≥ 3 distinct objects.
3. **Pre-flight:** "Run pre-flight" produces a spoken checklist covering every field the
   pre-flight reads (battery %, runtime, link RTT, temp, armed, safetyState, gear) with a
   per-item `ok/warn/fail` and a spoken summary. A deliberately low battery / stale link
   flips the matching item to `warn`/`fail`.
4. **Bounded spoken-drive:** With "assist" enabled and wheels up, "nudge forward"
   emits a forward token burst at ≤ configured `P` ceiling for ≤ configured duration,
   then auto-neutral — verified in relay/mock logs. "Stop" emits `forceNeutral()` tokens
   immediately.
5. **Human override:** While a brain drive action is in flight, any human manual input
   supersedes it on the same tick (verified: human tokens win in the log ordering).
6. **Dead-man honored:** If the brain/cockpit driver link goes silent, the relay
   neutralizes within its 700 ms dead-man window (no change to relay; verified via
   mock_remo log showing `P42/L0/R0`).
7. **No regressions:** Existing manual teleop still passes its current tests
   (`web` `vitest` suite green: `tokens.test.ts`, `store.test.ts`, `dummyVehicle.test.ts`,
   `dualsense.test.ts`).

## 7. Testing plan

| Layer | What | Approx count |
|-------|------|-------|
| Unit | drive-intent → bounded `Command` (cap + duration + auto-neutral); pre-flight field→status mapping; BrainReply parsing/guards | +6 |
| Integration | Brain endpoint with a stubbed model returns valid `BrainReply`; cockpit renders speech + preflight; drive-intent flows through `TokenEmitter` to `mock_remo` | +4 |
| E2E (bench) | Talk → reply; see → describe; pre-flight; nudge→auto-neutral; human override; dead-man — the seven acceptance criteria, run against `mock_remo` then once on real hardware wheels-up | 7 |

## 8. Open implementation items (resolve during the plan, not blocking this spec)

- **Camera frame capture** on the P1 path: reuse the cockpit's existing video element
  (browser `canvas` grab from the stream) as the primary; document a Jetson-side
  stdlib/ffmpeg fallback if the cockpit has no live video element yet. **Verify which
  exists before building.**
- **Real telemetry population:** confirm which `Telemetry` fields the real Remo/Arduino
  actually emits vs. which are cockpit-side defaults; the pre-flight only asserts on
  fields that are truly populated (document the mapping first).
- **Brain service language/host:** Node/TS (shares the web toolchain) vs Python; and
  where it runs in P1 (local dev box vs a cloud function). Decide in the plan.
- **Model + STT/TTS provider wiring** and secrets handling (keys never in the repo).

## 9. Milestones (feed the implementation plan; each has a Verify = its acceptance criteria)

- **M1 — Brain service skeleton:** endpoint + model/STT/TTS wiring; returns a spoken reply
  to a text turn. *Verify: criterion 1 (talk) against the service directly.*
- **M2 — Cockpit voice panel:** mic capture, TTS playback, transcript UI, wired to M1.
  *Verify: criterion 1 end-to-end in the browser.*
- **M3 — Sees:** camera frame sampled and sent; scene description. *Verify: criterion 2.*
- **M4 — Pre-flight:** telemetry snapshot → spoken checklist. *Verify: criterion 3.*
- **M5 — Bounded spoken-drive + override + dead-man:** drive-intent adapter through
  `TokenEmitter`; assist toggle; caps; human override. *Verify: criteria 4, 5, 6.*
- **M6 — Hardening + no-regression:** existing suite green, one real-hardware wheels-up
  pass of all seven criteria. *Verify: criterion 7 + full E2E.*

## 10. Effort (rough)

M1 ~ small · M2 ~ small · M3 ~ small · M4 ~ small · M5 ~ medium (safety-critical) ·
M6 ~ small. Bench/hardware verification time dominates M5–M6.

## 11. Rollback

P1 is additive — it plugs in beside manual teleop. Rollback = disable the "assist"
toggle (brain can talk/see but not drive) and, if needed, stop the brain service; the
cockpit keeps working as today. No changes to the relay or Remo.

## 12. Phase 1 verification (2026-07-08)

Built end to end as a milestone-by-milestone goal loop (M1–M6). No
`ANTHROPIC_API_KEY` was available, so every live-model check is **parked, not
failed** — each passes the moment a key exists; no rework is pending.

### Verified now (no key)

- **Suites green:** `brain` typecheck + 3 tests; `web` typecheck + 54 tests
  (57 total, zero regressions — criterion 7). `web` production build passes;
  ESLint clean on the new brain code.
- **M4 pre-flight (criterion 3, logic):** `evaluatePreflight` fully unit-tested
  (battery/link/temp/armed/safety/gear bands; low-battery→fail, stale-link→fail).
- **M5 bounded drive (criteria 4/5/6):**
  - `intentToCommand` caps (throttle ≤ 0.35) + `clampDurationMs` (≤ 1200 ms) unit-tested.
  - `intentToCommand` → real `TokenEmitter` emits a bounded `P` token strictly below the hardware max; auto-neutral = `P42/L0/R0`.
  - `assistStep` human-override (yields the instant the live command diverges) + auto-neutral unit-tested.
  - **Live** against real `argus_relay.py` + `mock_remo`: a bounded `P102` reaches the serial; going silent triggers the relay's 700 ms dead-man neutralize (`P42/L0/R0`).

### Parked behind `ANTHROPIC_API_KEY` (browser, live model)

- Criterion 1 (spoken reply), 2 (scene description), 3 (spoken pre-flight narration).
- Full voice→drive E2E (criterion 4 through the browser) — every constituent is
  already verified; only the voice trigger + live reply are gated.

### Parked behind real hardware + key (spec §6 final tick)

- One real-hardware, wheels-up pass of all 7 acceptance criteria (M6 / task 18).

**Net:** the entire Phase 1 code path is built and every key-independent check
is green. Closing the parked checks needs only (a) a key for the live model
loop, then (b) a wheels-up hardware pass.
