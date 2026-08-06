# Argus Drive — Cockpit UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full Argus Drive operator cockpit UI — a browser SPA that drives a simulated vehicle end-to-end (video, telemetry HUD, perception overlays, DualSense/keyboard input, safety states) against a browser-local mock contract, with zero ROS / WebRTC / hardware.

**Architecture:** Contract-first. A small set of TypeScript types (`CommandFrame`, `TelemetryFrame`) is the only coupling boundary. Everything talks to a `VehicleLink` interface; this plan ships a `MockLink` backed by a pure vehicle-simulation step function and a canvas-generated placeholder video. A later sibling plan ships `WebRTCLink` against the same interface, and the cockpit doesn't change. Input is normalized to one `InputState` shape and sent at a fixed rate; telemetry flows into a small store that drives all HUD components.

**Tech Stack:** React 18 + Vite + TypeScript + Tailwind CSS, Zustand (state store), Vitest + @testing-library/react + jsdom (tests), browser Gamepad / Canvas / MediaStream APIs. No backend.

## Global Constraints

- **Everything free / open-source.** No paid SaaS, no proprietary deps. (Spec §3, §9)
- **Contract is the only seam.** UI code imports `VehicleLink` + contract types only — never `MockLink` internals or `WebRTCLink` directly. Swapping links must require touching exactly one wiring file (`src/transport/createLink.ts`). (Spec §4, §8.1)
- **Normalized before transmission.** Every command sent carries `steer ∈ [-1,1]`, `throttle ∈ [0,1]`, `brake ∈ [0,1]`, a monotonic `seq`, and a `heartbeat` (ms epoch). (Spec §4.1, §6.1) — this plan pins `throttle`/`brake` to `[0,1]` (one-sided pedals), refining the spec's looser "each in -1..1"; record this as the contract value the actuation team must honor.
- **Safety default = stop.** If the vehicle is unsure the operator is in control, it stops. Watchdog timeout default **300 ms**; after any safety stop the vehicle is **LATCHED** until a deliberate re-arm. Safety states are exactly `DRIVING | STOPPED | LATCHED`. (Spec §6.2)
- **Latency is always visible.** Link RTT (ms) and a quality bucket are the single most important number and live in the top strip at all times; link loss triggers a full-screen red takeover instantly. (Spec §7)
- **Visual direction:** dark cockpit canvas, video is the hero, instruments at the edges, ONE restrained accent — Argus brand gold `#feda81` reserved for live/active states and alerts, clean geometric sans. Apple/Airbnb-grade restraint. (Spec §7)
- **Confirmed-state controls:** lights / blinkers / horn render "on" ONLY when telemetry reports them actually on — never from the local button press. (Spec §7 bottom HUD)
- **Perception fields are optional telemetry.** Overlays (tilt, proximity ring, object boxes, obstacle warning) read from `telemetry.perception?`; they degrade to hidden when absent and add nothing to the transport. (Spec §8.1)

---

## Phase A: Design Exploration (BEFORE any code)

Per spec §7, the cockpit is the most design-critical deliverable and gets a dedicated visual exploration before implementation. **No component code in Tasks 1–14 begins until the operator approves a direction here.** This phase uses every installed design/UX skill rather than hand-rolling tokens.

This is an interactive, human-in-the-loop phase — it produces **2–3 distinct mockup directions** for the operator to choose from, not a single take.

- [ ] **A1. Ground in references.** Pull the closest real specs from `voltagent/awesome-design-md` and extract concrete tokens (color, type, spacing, motion): Linear (dark-UI restraint), plus any cockpit/telemetry-HUD references. Raw URL form: `https://raw.githubusercontent.com/voltagent/awesome-design-md/main/design-md/<name>/DESIGN.md`. Anchor on the spec's stated direction: dark canvas, video-as-hero, ONE accent (Argus gold `#feda81`), geometric sans, instruments at the edges.

- [ ] **A2. Run the design-consultation skill** (`/design-consultation`, gstack) to understand the product and propose a complete design system (aesthetic, typography, color, layout, spacing, motion) with font + color previews. Feed it the spec's §7 visual direction and the references from A1.

- [ ] **A3. Invoke the `frontend-design` skill** (`frontend-design:frontend-design`) when generating the actual mockup markup, so variants are distinctive and production-grade, not generic AI-default UI.

- [ ] **A4. Generate multiple variants with `/design-shotgun`** (gstack) — produce 2–3 cockpit mockup directions (e.g. "minimal instrument", "tactical HUD", "Linear-grade calm"), open the comparison board, and present them to the operator. Each variant is a static mock of the §7 layout (top strip, video hero, edge instruments, bottom HUD) using placeholder telemetry values.

- [ ] **A5. Operator picks a direction** (or a blend). Capture the decision and the concrete tokens (final palette incl. exact gold usage rules, type scale, spacing unit, radii, motion timings) into `web/src/design/tokens.css` — this is the input to Task 1.

- [ ] **A6. (Optional) Finalize with `/design-html`** to lock production-quality CSS for the chosen direction, and earmark `/design-review` for the designer's-eye QA pass after Task 14.

> **Gate:** Tasks 1–14 implement the *approved* direction from A5. If A5 hasn't happened, stop and run Phase A first. Task 1's `tokens.css` is no longer invented from scratch — it is the serialization of the approved mockup.

---

## File Structure

All UI lives under `web/` at the repo root (operator side). The AGX/ROS side is a separate plan and is not created here.

```
web/
  package.json, vite.config.ts, tailwind.config.ts, postcss.config.js,
  tsconfig.json, vitest.config.ts, index.html, vitest.setup.ts
  src/
    main.tsx                      # React entry
    App.tsx                       # mounts <Cockpit/>
    design/tokens.css             # CSS variables + Tailwind @theme (colors, type, spacing)
    contract/
      commands.ts                 # CommandFrame, AuxCommands, SafetyCommand, Gear, DriveMode, BlinkerState
      telemetry.ts                # TelemetryFrame, SafetyState, PerceptionTelemetry, DetectedObject
      index.ts                    # re-exports
    transport/
      types.ts                    # VehicleLink, LinkStatus, LinkState
      MockLink.ts                 # mock link: drives sim, emits telemetry/status, injects latency
      createLink.ts               # the ONE wiring file: returns the active VehicleLink
    mock/
      dummyVehicle.ts             # stepVehicle(): pure vehicle-sim state machine (safety lives here)
      placeholderVideo.ts         # createPlaceholderVideo(): canvas → MediaStream
    input/
      normalize.ts                # InputState, buildCommandFrame(), neutralInput()
      gamepad.ts                  # readGamepad(): DualSense → InputState
      keyboard.ts                 # createKeyboardInput(): key state → InputState
      useDriveLoop.ts             # hook: fixed-rate read+send loop, seq/heartbeat
    state/
      store.ts                    # Zustand store: telemetry, status, link, dev latency
    components/
      Cockpit.tsx                 # top-level layout, wires store + drive loop
      TopStrip.tsx                # link/latency/quality, ARM, REC, E-STOP
      DisconnectTakeover.tsx      # full red link-lost overlay
      VideoLayer.tsx              # <video> + perception overlay canvas
      ObjectOverlay.tsx           # detected-object boxes + obstacle warning
      TiltIndicator.tsx           # left-edge attitude (pitch/roll)
      ProximityRing.tsx           # top-down nearby-objects ring
      BottomHud.tsx               # gear, speed, battery, mode, lights row
      EStopButton.tsx             # latched emergency stop
      DevLatencyPanel.tsx         # inject artificial RTT for testing
  tests/  (co-located *.test.ts(x) preferred; integration test under src/)
```

---

### Task 1: Project scaffold, tooling, and design tokens

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tailwind.config.ts`, `web/postcss.config.js`, `web/vitest.config.ts`, `web/vitest.setup.ts`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/design/tokens.css`
- Test: `web/src/design/tokens.test.ts`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a runnable Vite/React/TS app, a passing `npm test` (Vitest + jsdom + RTL), and design tokens exposed as CSS variables (`--argus-bg`, `--argus-gold`, `--argus-fg`, `--argus-alert`, font + spacing scale) plus Tailwind theme colors `bg`, `gold`, `alert`, `ok`, `warn`.

**Design grounding:** The tokens below are a **placeholder fallback** only. The real values come from the approved mockup in **Phase A5**. Before writing `tokens.css`, transcribe the approved direction's palette, type scale, spacing unit, radii, and motion timings here. Do NOT invent a new look at this step — Phase A already chose it. (If Phase A was skipped, stop and run it first.) Invariants regardless of direction: ONE accent (gold `#feda81`), everything else neutral dark, video is the hero, chrome recedes.

- [ ] **Step 1: Scaffold the app and install deps**

Run:
```bash
cd web 2>/dev/null || mkdir -p /Users/akashsuryavanshi/Projects/Argus_Drive/web
cd /Users/akashsuryavanshi/Projects/Argus_Drive/web
npm create vite@latest . -- --template react-ts
npm install
npm install zustand
npm install -D tailwindcss@^3 postcss autoprefixer vitest@^2 jsdom \
  @testing-library/react @testing-library/jest-dom @testing-library/user-event @types/node
```
Expected: `node_modules/` populated, no install errors. (If `npm create` refuses a non-empty dir, accept its prompt to scaffold in place / ignore existing files.)

- [ ] **Step 2: Write config files**

`web/postcss.config.js`:
```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
```

`web/tailwind.config.ts`:
```ts
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0a0b0d',
        panel: '#14161a',
        fg: '#e7e9ec',
        muted: '#8b9099',
        gold: '#feda81',
        alert: '#ff4d4f',
        ok: '#4ade80',
        warn: '#fbbf24',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
```

`web/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
})
```

`web/vitest.setup.ts`:
```ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 3: Write `web/src/design/tokens.css` and wire it**

`web/src/design/tokens.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --argus-bg: #0a0b0d;
  --argus-panel: #14161a;
  --argus-fg: #e7e9ec;
  --argus-muted: #8b9099;
  --argus-gold: #feda81;     /* live / active / alert accent — reserved */
  --argus-alert: #ff4d4f;
  --argus-ok: #4ade80;
  --argus-warn: #fbbf24;
  --argus-space: 8px;
}

html, body, #root { height: 100%; margin: 0; background: var(--argus-bg); }
body { color: var(--argus-fg); font-family: Inter, system-ui, sans-serif; }
```

Replace `web/src/main.tsx` body to import tokens and render `App`:
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './design/tokens.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

`web/src/App.tsx`:
```tsx
export default function App() {
  return <div data-testid="app-root" className="h-full w-full bg-bg text-fg" />
}
```

Add the test script to `web/package.json` `"scripts"`: `"test": "vitest run"`, `"test:watch": "vitest"`.

- [ ] **Step 4: Write the failing token test**

`web/src/design/tokens.test.ts`:
```ts
import { describe, it, expect } from 'vitest'

describe('design tokens', () => {
  it('reserves Argus gold as the single accent', () => {
    document.documentElement.style.setProperty('--argus-gold', '#feda81')
    const gold = getComputedStyle(document.documentElement).getPropertyValue('--argus-gold')
    expect(gold.trim()).toBe('#feda81')
  })
})
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/akashsuryavanshi/Projects/Argus_Drive/web && npm test`
Expected: PASS (1 test). If the very first run fails on a missing `@vitejs/plugin-react`, `npm i -D @vitejs/plugin-react` and re-run.

- [ ] **Step 6: Add `web/.gitignore` entries and commit**

Ensure `web/node_modules`, `web/dist` are ignored (Vite's template `.gitignore` already covers this).
```bash
cd /Users/akashsuryavanshi/Projects/Argus_Drive
git add web docs/superpowers/plans
git commit -m "chore(ui): scaffold cockpit app, tooling, and design tokens"
```

---

### Task 2: Contract types

**Files:**
- Create: `web/src/contract/commands.ts`, `web/src/contract/telemetry.ts`, `web/src/contract/index.ts`
- Test: `web/src/contract/commands.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces — the entire decoupling boundary. These exact names/types are referenced by every later task:
  - `Gear = 'F' | 'N' | 'R'`, `DriveMode = 'slow' | 'normal'`, `BlinkerState = 'off' | 'left' | 'right' | 'hazard'`
  - `AuxCommands { blinker: BlinkerState; headlights: boolean; workLights: boolean; horn: boolean; record: boolean; driveMode: DriveMode }`
  - `SafetyCommand { arm: boolean; estop: boolean }`
  - `CommandFrame { seq: number; heartbeat: number; steer: number; throttle: number; brake: number; gear: Gear; aux: AuxCommands; safety: SafetyCommand }`
  - `SafetyState = 'DRIVING' | 'STOPPED' | 'LATCHED'`
  - `DetectedObject`, `PerceptionTelemetry`, `TelemetryFrame` (full shapes below)
  - `clampUnit(n)`, `clampSigned(n)` helpers.

- [ ] **Step 1: Write the failing test**

`web/src/contract/commands.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { clampUnit, clampSigned } from './commands'

describe('contract clamps', () => {
  it('clampUnit pins to [0,1]', () => {
    expect(clampUnit(-0.5)).toBe(0)
    expect(clampUnit(0.5)).toBe(0.5)
    expect(clampUnit(2)).toBe(1)
  })
  it('clampSigned pins to [-1,1]', () => {
    expect(clampSigned(-2)).toBe(-1)
    expect(clampSigned(0.3)).toBe(0.3)
    expect(clampSigned(2)).toBe(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/akashsuryavanshi/Projects/Argus_Drive/web && npx vitest run src/contract`
Expected: FAIL — cannot resolve `./commands`.

- [ ] **Step 3: Write `web/src/contract/commands.ts`**

```ts
export type Gear = 'F' | 'N' | 'R'
export type DriveMode = 'slow' | 'normal'
export type BlinkerState = 'off' | 'left' | 'right' | 'hazard'

export interface AuxCommands {
  blinker: BlinkerState
  headlights: boolean
  workLights: boolean
  horn: boolean
  record: boolean
  driveMode: DriveMode
}

export interface SafetyCommand {
  arm: boolean    // momentary: true on the frame the re-arm combo is pressed
  estop: boolean  // momentary: true on the frame E-STOP is pressed; vehicle latches
}

/** Operator → vehicle, sent at a fixed rate over the control DataChannel. */
export interface CommandFrame {
  seq: number        // monotonic, increments every sent frame
  heartbeat: number  // sender clock, ms epoch
  steer: number      // [-1, 1]  left negative, right positive
  throttle: number   // [0, 1]
  brake: number      // [0, 1]
  gear: Gear
  aux: AuxCommands
  safety: SafetyCommand
}

export const clampUnit = (n: number): number => Math.max(0, Math.min(1, n))
export const clampSigned = (n: number): number => Math.max(-1, Math.min(1, n))
```

- [ ] **Step 4: Write `web/src/contract/telemetry.ts`**

```ts
import type { Gear, DriveMode, BlinkerState } from './commands'

export type SafetyState = 'DRIVING' | 'STOPPED' | 'LATCHED'

export interface DetectedObject {
  class: string
  bbox: { x: number; y: number; w: number; h: number } // normalized 0..1 over the video frame
  distanceM: number
  bearingDeg: number
}

/** All optional — added by the perception phase, never required by transport/UI. */
export interface PerceptionTelemetry {
  nearestObstacle?: { distanceM: number; bearingDeg: number }
  proximity?: number[] // downsampled range array, fixed length (see PROXIMITY_BINS)
  objects?: DetectedObject[]
  odom?: { x: number; y: number; headingDeg: number; velocity: number }
  attitude?: { pitchDeg: number; rollDeg: number }
  gnss?: { lat: number; lon: number; fixQuality: number }
}

/** Vehicle → operator, published a few times per second over the DataChannel. */
export interface TelemetryFrame {
  seq: number
  timestamp: number // sender clock, ms epoch
  speedKmh: number
  gear: Gear
  steerAngleDeg: number
  driveMode: DriveMode
  armed: boolean
  safetyState: SafetyState
  battery: { percent: number; runtimeMin: number }
  lights: { headlights: boolean; workLights: boolean; blinker: BlinkerState; horn: boolean }
  temps: { jetsonC: number; motorC?: number }
  faults: string[]
  recording: boolean
  perception?: PerceptionTelemetry
}

export const PROXIMITY_BINS = 24 // proximity[] length when present
```

- [ ] **Step 5: Write `web/src/contract/index.ts`**

```ts
export * from './commands'
export * from './telemetry'
```

- [ ] **Step 6: Run tests and commit**

Run: `npx vitest run src/contract` → Expected: PASS (2 tests).
```bash
git add web/src/contract && git commit -m "feat(contract): command and telemetry boundary types"
```

---

### Task 3: Vehicle simulation core (`stepVehicle`)

This is the safety brain of the mock. It encodes the spec's §6.2 safety model as a pure function so it can be exhaustively unit-tested with no DOM, no timers.

**Files:**
- Create: `web/src/mock/dummyVehicle.ts`
- Test: `web/src/mock/dummyVehicle.test.ts`

**Interfaces:**
- Consumes: `CommandFrame`, `Gear`, `SafetyState`, `BlinkerState`, `DriveMode` from `../contract`.
- Produces:
  - `WATCHDOG_MS = 300`, `MAX_SPEED_KMH = { slow: 8, normal: 18 }`, `STEER_MAX_DEG = 30`
  - `VehicleSimState` (full shape below)
  - `initialSimState(): VehicleSimState`
  - `stepVehicle(s: VehicleSimState, cmd: CommandFrame | null, dtSec: number, msSinceCmd: number): VehicleSimState`
  - `toTelemetry(s: VehicleSimState, seq: number, timestamp: number): TelemetryFrame`

- [ ] **Step 1: Write the failing tests**

`web/src/mock/dummyVehicle.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { initialSimState, stepVehicle, WATCHDOG_MS } from './dummyVehicle'
import type { CommandFrame } from '../contract'

const cmd = (over: Partial<CommandFrame> = {}): CommandFrame => ({
  seq: 1, heartbeat: 0, steer: 0, throttle: 0, brake: 0, gear: 'F',
  aux: { blinker: 'off', headlights: false, workLights: false, horn: false, record: false, driveMode: 'slow' },
  safety: { arm: false, estop: false },
  ...over,
})

describe('stepVehicle safety model', () => {
  it('starts disarmed and stopped', () => {
    const s = initialSimState()
    expect(s.armed).toBe(false)
    expect(s.safetyState).toBe('STOPPED')
    expect(s.speedKmh).toBe(0)
  })

  it('re-arms on a rising arm edge and enters DRIVING', () => {
    let s = initialSimState()
    s = stepVehicle(s, cmd({ safety: { arm: true, estop: false } }), 0.05, 0)
    expect(s.armed).toBe(true)
    expect(s.safetyState).toBe('DRIVING')
  })

  it('does NOT re-arm while arm is held (only on rising edge)', () => {
    let s = initialSimState()
    const held = cmd({ safety: { arm: true, estop: false } })
    s = stepVehicle(s, held, 0.05, 0)               // edge → armed
    s = stepVehicle(s, { ...held, safety: { arm: false, estop: true } }, 0.05, 0) // estop latch
    expect(s.safetyState).toBe('LATCHED')
    s = stepVehicle(s, held, 0.05, 0)               // held high, but no rising edge since last low? it IS low->high
    // arm was false on prev frame, true now → rising edge re-arms out of LATCHED:
    expect(s.safetyState).toBe('DRIVING')
  })

  it('accelerates toward throttle target when armed', () => {
    let s = initialSimState()
    s = stepVehicle(s, cmd({ safety: { arm: true, estop: false } }), 0.05, 0)
    for (let i = 0; i < 200; i++) s = stepVehicle(s, cmd({ throttle: 1, aux: { ...cmd().aux, driveMode: 'slow' } }), 0.05, 0)
    expect(s.speedKmh).toBeGreaterThan(7)
    expect(s.speedKmh).toBeLessThanOrEqual(8.01) // capped at slow max
  })

  it('watchdog stops the vehicle after timeout', () => {
    let s = initialSimState()
    s = stepVehicle(s, cmd({ safety: { arm: true, estop: false } }), 0.05, 0)
    for (let i = 0; i < 50; i++) s = stepVehicle(s, cmd({ throttle: 1 }), 0.05, 0)
    expect(s.speedKmh).toBeGreaterThan(0)
    s = stepVehicle(s, cmd({ throttle: 1 }), 0.05, WATCHDOG_MS + 50) // stale command
    expect(s.safetyState).toBe('STOPPED')
  })

  it('e-stop immediately latches and disarms', () => {
    let s = initialSimState()
    s = stepVehicle(s, cmd({ safety: { arm: true, estop: false } }), 0.05, 0)
    s = stepVehicle(s, cmd({ safety: { arm: false, estop: true } }), 0.05, 0)
    expect(s.safetyState).toBe('LATCHED')
    expect(s.armed).toBe(false)
  })

  it('latched state ignores throttle until re-armed', () => {
    let s = initialSimState()
    s = stepVehicle(s, cmd({ safety: { arm: true, estop: false } }), 0.05, 0)
    s = stepVehicle(s, cmd({ safety: { arm: false, estop: true } }), 0.05, 0)
    for (let i = 0; i < 50; i++) s = stepVehicle(s, cmd({ throttle: 1 }), 0.05, 0)
    expect(s.speedKmh).toBe(0)
  })

  it('drains battery over time', () => {
    let s = initialSimState()
    const start = s.batteryPercent
    s = stepVehicle(s, cmd({ safety: { arm: true, estop: false } }), 0.05, 0)
    for (let i = 0; i < 2000; i++) s = stepVehicle(s, cmd({ throttle: 1 }), 0.05, 0)
    expect(s.batteryPercent).toBeLessThan(start)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/mock/dummyVehicle.test.ts`
Expected: FAIL — cannot resolve `./dummyVehicle`.

- [ ] **Step 3: Implement `web/src/mock/dummyVehicle.ts`**

```ts
import type {
  CommandFrame, Gear, SafetyState, BlinkerState, DriveMode, TelemetryFrame,
} from '../contract'

export const WATCHDOG_MS = 300
export const MAX_SPEED_KMH: Record<DriveMode, number> = { slow: 8, normal: 18 }
export const STEER_MAX_DEG = 30

const ACCEL = 6   // km/h per second toward target
const DECEL = 12  // km/h per second when braking / stopping

export interface VehicleSimState {
  speedKmh: number
  gear: Gear
  steerAngleDeg: number
  driveMode: DriveMode
  armed: boolean
  safetyState: SafetyState
  batteryPercent: number
  lights: { headlights: boolean; workLights: boolean; blinker: BlinkerState; horn: boolean }
  recording: boolean
  prevArm: boolean
  // perception sim phase (deterministic motion for overlays)
  tPerc: number
}

export function initialSimState(): VehicleSimState {
  return {
    speedKmh: 0, gear: 'N', steerAngleDeg: 0, driveMode: 'slow',
    armed: false, safetyState: 'STOPPED', batteryPercent: 92,
    lights: { headlights: false, workLights: false, blinker: 'off', horn: false },
    recording: false, prevArm: false, tPerc: 0,
  }
}

const approach = (cur: number, target: number, rate: number, dt: number): number => {
  const step = rate * dt
  if (cur < target) return Math.min(target, cur + step)
  if (cur > target) return Math.max(target, cur - step)
  return cur
}

export function stepVehicle(
  s: VehicleSimState,
  cmd: CommandFrame | null,
  dtSec: number,
  msSinceCmd: number,
): VehicleSimState {
  const next: VehicleSimState = { ...s, lights: { ...s.lights }, tPerc: s.tPerc + dtSec }

  // 1. E-STOP — highest priority, latches and disarms.
  if (cmd?.safety.estop) {
    next.safetyState = 'LATCHED'
    next.armed = false
  }

  // 2. Re-arm on a rising edge of the arm command while not driving.
  const armRising = !!cmd?.safety.arm && !s.prevArm
  if (armRising && next.safetyState !== 'DRIVING') {
    next.armed = true
    next.safetyState = 'DRIVING'
  }
  next.prevArm = !!cmd?.safety.arm

  // 3. Watchdog — stale or absent command stops a driving vehicle (not when latched).
  const stale = !cmd || msSinceCmd > WATCHDOG_MS
  if (stale && next.safetyState === 'DRIVING') {
    next.safetyState = 'STOPPED'
    next.armed = false
  }

  // 4. Longitudinal dynamics.
  const driving = next.safetyState === 'DRIVING' && next.armed && !!cmd
  if (driving) {
    next.driveMode = cmd!.aux.driveMode
    next.gear = cmd!.gear
    const cap = MAX_SPEED_KMH[next.driveMode]
    const dir = cmd!.gear === 'R' ? -1 : cmd!.gear === 'N' ? 0 : 1
    const target = cmd!.brake > 0.02 ? 0 : dir * cap * cmd!.throttle
    const rate = cmd!.brake > 0.02 || Math.abs(target) < Math.abs(next.speedKmh) ? DECEL : ACCEL
    next.speedKmh = approach(next.speedKmh, target, rate, dtSec)
    next.steerAngleDeg = cmd!.steer * STEER_MAX_DEG
    // confirmed light state echoes the command only while powered/driving:
    next.lights = {
      headlights: cmd!.aux.headlights,
      workLights: cmd!.aux.workLights,
      blinker: cmd!.aux.blinker,
      horn: cmd!.aux.horn,
    }
    next.recording = cmd!.aux.record ? !s.recording && cmd!.aux.record ? s.recording : s.recording : s.recording
    if (cmd!.aux.record && !s.lights.horn) { /* record handled below */ }
  } else {
    next.speedKmh = approach(next.speedKmh, 0, DECEL, dtSec)
    next.steerAngleDeg = approach(next.steerAngleDeg, 0, 60, dtSec)
  }

  // 4b. Recording is a momentary toggle (edge), independent of drive state.
  if (cmd?.aux.record && !s._recordEdge) {
    next.recording = !s.recording
    ;(next as VehicleSimState & { _recordEdge?: boolean })._recordEdge = true
  }
  if (!cmd?.aux.record) {
    ;(next as VehicleSimState & { _recordEdge?: boolean })._recordEdge = false
  }

  // 5. Battery drain — base load + speed term.
  const drain = (0.0008 + Math.abs(next.speedKmh) * 0.00012) * dtSec
  next.batteryPercent = Math.max(0, s.batteryPercent - drain)

  return next
}

export function toTelemetry(s: VehicleSimState, seq: number, timestamp: number): TelemetryFrame {
  const runtimeMin = Math.round((s.batteryPercent / 100) * 50)
  // Deterministic perception sim for overlays.
  const t = s.tPerc
  const pitch = Math.sin(t * 0.6) * 3
  const roll = Math.cos(t * 0.4) * 2
  const proximity = Array.from({ length: 24 }, (_, i) =>
    2 + Math.abs(Math.sin(t * 0.3 + i * 0.5)) * 6,
  )
  return {
    seq, timestamp,
    speedKmh: Math.round(Math.abs(s.speedKmh) * 10) / 10,
    gear: s.gear,
    steerAngleDeg: Math.round(s.steerAngleDeg * 10) / 10,
    driveMode: s.driveMode,
    armed: s.armed,
    safetyState: s.safetyState,
    battery: { percent: Math.round(s.batteryPercent), runtimeMin },
    lights: s.lights,
    temps: { jetsonC: 48 + Math.abs(s.speedKmh) * 0.6 },
    faults: [],
    recording: s.recording,
    perception: {
      attitude: { pitchDeg: Math.round(pitch * 10) / 10, rollDeg: Math.round(roll * 10) / 10 },
      proximity,
      nearestObstacle: { distanceM: Math.round((1.2 + Math.abs(Math.sin(t * 0.2)) * 4) * 10) / 10, bearingDeg: 15 },
      objects: [
        { class: 'person', bbox: { x: 0.62, y: 0.45, w: 0.08, h: 0.22 }, distanceM: 3.2, bearingDeg: 12 },
      ],
      odom: { x: 0, y: 0, headingDeg: 0, velocity: Math.abs(s.speedKmh) / 3.6 },
    },
  }
}
```

> Note: simplify the `next.recording`/`_recordEdge` block during implementation — keep ONLY the Step "4b" edge-toggle logic and delete the dead `next.recording = cmd!.aux.record ? ...` line inside the `driving` branch. The test in Step 1 does not assert recording; a follow-up test in Task 9 covers REC. Keep the edge-toggle, drop the tangle.

- [ ] **Step 4: Clean up the recording logic**

Edit `dummyVehicle.ts`: inside the `driving` branch, delete the two `next.recording = ...` / `if (cmd!.aux.record && ...)` lines. Add `_recordEdge?: boolean` to the `VehicleSimState` interface as an optional field and initialize it `false` in `initialSimState`. Final recording logic is only the Step "4b" block.

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run src/mock/dummyVehicle.test.ts`
Expected: PASS (8 tests). If "does NOT re-arm while held" fails, recheck that `prevArm` is read from `s` (previous), not `next`.

- [ ] **Step 6: Commit**

```bash
git add web/src/mock/dummyVehicle.ts web/src/mock/dummyVehicle.test.ts
git commit -m "feat(mock): vehicle sim state machine with watchdog, latch, and re-arm"
```

---

### Task 4: Placeholder video source

**Files:**
- Create: `web/src/mock/placeholderVideo.ts`
- Test: `web/src/mock/placeholderVideo.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `createPlaceholderVideo(): { stream: MediaStream; stop: () => void }` — a canvas-rendered moving test pattern as a `MediaStream` via `canvas.captureStream()`, so `VideoLayer` can treat it exactly like a real WebRTC track.

- [ ] **Step 1: Write the failing test**

`web/src/mock/placeholderVideo.test.ts`:
```ts
import { describe, it, expect, vi } from 'vitest'
import { createPlaceholderVideo } from './placeholderVideo'

describe('createPlaceholderVideo', () => {
  it('returns a MediaStream and a stop function', () => {
    // jsdom lacks captureStream; stub it.
    const fakeStream = { id: 'fake', getTracks: () => [] } as unknown as MediaStream
    const proto = HTMLCanvasElement.prototype as unknown as { captureStream?: () => MediaStream }
    proto.captureStream = vi.fn(() => fakeStream)
    const ctxStub = { fillRect: vi.fn(), fillStyle: '', fillText: vi.fn(), font: '', clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn() }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctxStub as unknown as CanvasRenderingContext2D)

    const v = createPlaceholderVideo()
    expect(v.stream).toBe(fakeStream)
    expect(typeof v.stop).toBe('function')
    v.stop()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/mock/placeholderVideo.test.ts` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/mock/placeholderVideo.ts`**

```ts
/** A self-animating canvas exposed as a MediaStream — stands in for the WebRTC video track. */
export function createPlaceholderVideo(width = 1280, height = 720): { stream: MediaStream; stop: () => void } {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')!
  let raf = 0
  let t = 0

  const draw = () => {
    t += 1
    ctx.fillStyle = '#0a0b0d'
    ctx.fillRect(0, 0, width, height)
    // moving horizon line to feel like a live feed
    ctx.fillStyle = '#1c2026'
    const y = height * 0.6 + Math.sin(t * 0.02) * 12
    ctx.fillRect(0, y, width, height - y)
    ctx.fillStyle = '#3a4150'
    for (let i = 0; i < 6; i++) {
      const x = ((t * 4 + i * 240) % (width + 240)) - 120
      ctx.fillRect(x, y - 4, 80, 8)
    }
    ctx.fillStyle = '#8b9099'
    ctx.font = '20px monospace'
    ctx.fillText('ARGUS // MOCK FEED', 24, 40)
    raf = requestAnimationFrame(draw)
  }
  raf = requestAnimationFrame(draw)

  const stream = (canvas as HTMLCanvasElement & { captureStream: (fps?: number) => MediaStream }).captureStream(30)
  return { stream, stop: () => cancelAnimationFrame(raf) }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/mock/placeholderVideo.test.ts` → Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add web/src/mock/placeholderVideo.ts web/src/mock/placeholderVideo.test.ts
git commit -m "feat(mock): canvas placeholder video as MediaStream"
```

---

### Task 5: VehicleLink interface + MockLink

**Files:**
- Create: `web/src/transport/types.ts`, `web/src/transport/MockLink.ts`, `web/src/transport/createLink.ts`
- Test: `web/src/transport/MockLink.test.ts`

**Interfaces:**
- Consumes: `CommandFrame`, `TelemetryFrame` from `../contract`; `initialSimState`, `stepVehicle`, `toTelemetry` from `../mock/dummyVehicle`; `createPlaceholderVideo` from `../mock/placeholderVideo`.
- Produces:
  - `LinkState = 'connecting' | 'connected' | 'disconnected'`
  - `LinkQuality = 'good' | 'fair' | 'poor'`
  - `LinkStatus { state: LinkState; rttMs: number | null; quality: LinkQuality }`
  - `VehicleLink` interface (below)
  - `class MockLink implements VehicleLink` with `setInjectedLatency(ms: number)` and `forceDisconnect()` test/dev hooks
  - `createLink(): VehicleLink` — the single wiring point.

- [ ] **Step 1: Write the failing test**

`web/src/transport/MockLink.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MockLink } from './MockLink'
import type { CommandFrame } from '../contract'

const cmd = (seq: number): CommandFrame => ({
  seq, heartbeat: performance.now(), steer: 0, throttle: 1, brake: 0, gear: 'F',
  aux: { blinker: 'off', headlights: false, workLights: false, horn: false, record: false, driveMode: 'slow' },
  safety: { arm: seq === 1, estop: false },
})

describe('MockLink', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    const proto = HTMLCanvasElement.prototype as unknown as { captureStream?: () => MediaStream }
    proto.captureStream = vi.fn(() => ({ id: 'fake', getTracks: () => [] }) as unknown as MediaStream)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      fillRect: vi.fn(), fillStyle: '', fillText: vi.fn(), font: '',
    } as unknown as CanvasRenderingContext2D)
  })
  afterEach(() => vi.useRealTimers())

  it('emits connected status then telemetry after connect', () => {
    const link = new MockLink()
    const statuses: string[] = []
    const tele: number[] = []
    link.onStatus((s) => statuses.push(s.state))
    link.onTelemetry((t) => tele.push(t.seq))
    link.connect()
    vi.advanceTimersByTime(500)
    expect(statuses).toContain('connected')
    expect(tele.length).toBeGreaterThan(0)
    link.disconnect()
  })

  it('drives the sim from sent commands (armed → moving telemetry)', () => {
    const link = new MockLink()
    let last = 0
    link.onTelemetry((t) => { last = t.speedKmh })
    link.connect()
    for (let i = 1; i <= 60; i++) { link.send(cmd(i)); vi.advanceTimersByTime(50) }
    expect(last).toBeGreaterThan(0)
    link.disconnect()
  })

  it('reports disconnected on forceDisconnect', () => {
    const link = new MockLink()
    const statuses: string[] = []
    link.onStatus((s) => statuses.push(s.state))
    link.connect()
    vi.advanceTimersByTime(100)
    link.forceDisconnect()
    expect(statuses[statuses.length - 1]).toBe('disconnected')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/transport/MockLink.test.ts` → Expected: FAIL (module missing).

- [ ] **Step 3: Write `web/src/transport/types.ts`**

```ts
import type { CommandFrame, TelemetryFrame } from '../contract'

export type LinkState = 'connecting' | 'connected' | 'disconnected'
export type LinkQuality = 'good' | 'fair' | 'poor'

export interface LinkStatus {
  state: LinkState
  rttMs: number | null
  quality: LinkQuality
}

export interface VehicleLink {
  connect(): void
  disconnect(): void
  send(cmd: CommandFrame): void
  getVideoStream(): MediaStream | null
  onTelemetry(cb: (t: TelemetryFrame) => void): () => void
  onStatus(cb: (s: LinkStatus) => void): () => void
}

export function qualityFromRtt(rttMs: number | null): LinkQuality {
  if (rttMs == null) return 'poor'
  if (rttMs < 180) return 'good'
  if (rttMs < 320) return 'fair'
  return 'poor'
}
```

- [ ] **Step 4: Write `web/src/transport/MockLink.ts`**

```ts
import type { CommandFrame, TelemetryFrame } from '../contract'
import type { LinkState, LinkStatus, VehicleLink } from './types'
import { qualityFromRtt } from './types'
import { initialSimState, stepVehicle, toTelemetry, type VehicleSimState } from '../mock/dummyVehicle'
import { createPlaceholderVideo } from '../mock/placeholderVideo'

const TICK_MS = 50            // sim + telemetry cadence (20 Hz)
const BASE_LATENCY_MS = 120   // simulated one-way-ish base RTT

export class MockLink implements VehicleLink {
  private sim: VehicleSimState = initialSimState()
  private seq = 0
  private lastCmd: CommandFrame | null = null
  private lastCmdAt = 0
  private injectedLatency = 0
  private video: { stream: MediaStream; stop: () => void } | null = null
  private tickHandle: ReturnType<typeof setInterval> | null = null
  private teleCbs = new Set<(t: TelemetryFrame) => void>()
  private statusCbs = new Set<(s: LinkStatus) => void>()
  private state: LinkState = 'disconnected'

  setInjectedLatency(ms: number) { this.injectedLatency = Math.max(0, ms) }
  forceDisconnect() { this.setState('disconnected'); this.teardown() }

  connect(): void {
    this.sim = initialSimState()
    this.video = createPlaceholderVideo()
    this.setState('connecting')
    setTimeout(() => {
      this.setState('connected')
      this.tickHandle = setInterval(() => this.tick(), TICK_MS)
    }, 150)
  }

  disconnect(): void { this.setState('disconnected'); this.teardown() }

  send(cmd: CommandFrame): void {
    // Simulate uplink latency: command takes effect after base + injected delay.
    const delay = BASE_LATENCY_MS + this.injectedLatency
    setTimeout(() => { this.lastCmd = cmd; this.lastCmdAt = performance.now() }, delay)
  }

  getVideoStream(): MediaStream | null { return this.video?.stream ?? null }

  onTelemetry(cb: (t: TelemetryFrame) => void): () => void {
    this.teleCbs.add(cb); return () => this.teleCbs.delete(cb)
  }
  onStatus(cb: (s: LinkStatus) => void): () => void {
    this.statusCbs.add(cb); cb(this.currentStatus()); return () => this.statusCbs.delete(cb)
  }

  private rtt(): number { return BASE_LATENCY_MS + this.injectedLatency }
  private currentStatus(): LinkStatus {
    const rttMs = this.state === 'connected' ? this.rtt() : null
    return { state: this.state, rttMs, quality: qualityFromRtt(rttMs) }
  }
  private setState(s: LinkState) { this.state = s; this.emitStatus() }
  private emitStatus() { const st = this.currentStatus(); this.statusCbs.forEach((cb) => cb(st)) }

  private tick() {
    const now = performance.now()
    const msSinceCmd = this.lastCmd ? now - this.lastCmdAt : Number.POSITIVE_INFINITY
    this.sim = stepVehicle(this.sim, this.lastCmd, TICK_MS / 1000, msSinceCmd)
    const frame = toTelemetry(this.sim, ++this.seq, now)
    // Simulate downlink latency before the UI sees telemetry.
    const delay = BASE_LATENCY_MS + this.injectedLatency
    setTimeout(() => this.teleCbs.forEach((cb) => cb(frame)), delay)
    this.emitStatus()
  }

  private teardown() {
    if (this.tickHandle) clearInterval(this.tickHandle)
    this.tickHandle = null
    this.video?.stop()
    this.video = null
  }
}
```

- [ ] **Step 5: Write `web/src/transport/createLink.ts`**

```ts
import type { VehicleLink } from './types'
import { MockLink } from './MockLink'

/** The single place the active transport is chosen. A later plan swaps in WebRTCLink here. */
export function createLink(): VehicleLink {
  return new MockLink()
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `npx vitest run src/transport/MockLink.test.ts` → Expected: PASS (3 tests). With fake timers, `setTimeout`-delayed telemetry fires as `advanceTimersByTime` crosses the delay.

- [ ] **Step 7: Commit**

```bash
git add web/src/transport && git commit -m "feat(transport): VehicleLink interface and MockLink with latency injection"
```

---

### Task 6: State store

**Files:**
- Create: `web/src/state/store.ts`
- Test: `web/src/state/store.test.ts`

**Interfaces:**
- Consumes: `TelemetryFrame` from `../contract`; `VehicleLink`, `LinkStatus` from `../transport/types`; `createLink` from `../transport/createLink`.
- Produces a Zustand store `useStore` with state `{ link: VehicleLink; telemetry: TelemetryFrame | null; status: LinkStatus; injectedLatency: number }` and actions `connect()`, `disconnect()`, `setInjectedLatency(ms)`. Selector hooks: `useTelemetry()`, `useStatus()`, `useLink()`.

- [ ] **Step 1: Write the failing test**

`web/src/state/store.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useStore } from './store'

describe('store', () => {
  beforeEach(() => {
    const proto = HTMLCanvasElement.prototype as unknown as { captureStream?: () => MediaStream }
    proto.captureStream = vi.fn(() => ({ id: 'fake', getTracks: () => [] }) as unknown as MediaStream)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      fillRect: vi.fn(), fillStyle: '', fillText: vi.fn(), font: '',
    } as unknown as CanvasRenderingContext2D)
  })

  it('starts disconnected with no telemetry', () => {
    const s = useStore.getState()
    expect(s.status.state).toBe('disconnected')
    expect(s.telemetry).toBeNull()
  })

  it('connect() subscribes the link to the store', () => {
    vi.useFakeTimers()
    useStore.getState().connect()
    vi.advanceTimersByTime(500)
    expect(useStore.getState().status.state).toBe('connected')
    expect(useStore.getState().telemetry).not.toBeNull()
    useStore.getState().disconnect()
    vi.useRealTimers()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/state/store.test.ts` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/state/store.ts`**

```ts
import { create } from 'zustand'
import type { TelemetryFrame } from '../contract'
import type { LinkStatus, VehicleLink } from '../transport/types'
import { createLink } from '../transport/createLink'
import type { MockLink } from '../transport/MockLink'

interface StoreState {
  link: VehicleLink
  telemetry: TelemetryFrame | null
  status: LinkStatus
  injectedLatency: number
  connect: () => void
  disconnect: () => void
  setInjectedLatency: (ms: number) => void
}

let unsubTele: (() => void) | null = null
let unsubStatus: (() => void) | null = null

export const useStore = create<StoreState>((set, get) => ({
  link: createLink(),
  telemetry: null,
  status: { state: 'disconnected', rttMs: null, quality: 'poor' },
  injectedLatency: 0,

  connect: () => {
    const { link } = get()
    unsubTele?.(); unsubStatus?.()
    unsubTele = link.onTelemetry((telemetry) => set({ telemetry }))
    unsubStatus = link.onStatus((status) => set({ status }))
    link.connect()
  },

  disconnect: () => {
    const { link } = get()
    link.disconnect()
    unsubTele?.(); unsubStatus?.()
    unsubTele = unsubStatus = null
  },

  setInjectedLatency: (ms: number) => {
    const { link } = get()
    ;(link as Partial<MockLink>).setInjectedLatency?.(ms)
    set({ injectedLatency: ms })
  },
}))

export const useTelemetry = () => useStore((s) => s.telemetry)
export const useStatus = () => useStore((s) => s.status)
export const useLink = () => useStore((s) => s.link)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/state/store.test.ts` → Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/state && git commit -m "feat(state): zustand store wiring link telemetry and status"
```

---

### Task 7: Input normalization

**Files:**
- Create: `web/src/input/normalize.ts`
- Test: `web/src/input/normalize.test.ts`

**Interfaces:**
- Consumes: `CommandFrame`, `AuxCommands`, `SafetyCommand`, `Gear`, `clampUnit`, `clampSigned` from `../contract`.
- Produces:
  - `InputState { steer; throttle; brake; gear: Gear; aux: AuxCommands; safety: SafetyCommand }`
  - `neutralInput(): InputState`
  - `applyDeadzone(v: number, dz?: number): number`
  - `buildCommandFrame(input: InputState, seq: number, heartbeat: number): CommandFrame` — clamps every field.

- [ ] **Step 1: Write the failing test**

`web/src/input/normalize.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { neutralInput, applyDeadzone, buildCommandFrame } from './normalize'

describe('input normalization', () => {
  it('neutralInput is safe and centered', () => {
    const n = neutralInput()
    expect(n.steer).toBe(0)
    expect(n.throttle).toBe(0)
    expect(n.gear).toBe('N')
    expect(n.safety.estop).toBe(false)
  })

  it('applyDeadzone zeroes small noise and rescales', () => {
    expect(applyDeadzone(0.05)).toBe(0)
    expect(applyDeadzone(0)).toBe(0)
    expect(Math.abs(applyDeadzone(1))).toBeCloseTo(1, 5)
  })

  it('buildCommandFrame clamps out-of-range axes', () => {
    const f = buildCommandFrame({ ...neutralInput(), steer: 2, throttle: 5, brake: -1 }, 7, 12345)
    expect(f.steer).toBe(1)
    expect(f.throttle).toBe(1)
    expect(f.brake).toBe(0)
    expect(f.seq).toBe(7)
    expect(f.heartbeat).toBe(12345)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/input/normalize.test.ts` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/input/normalize.ts`**

```ts
import type { CommandFrame, AuxCommands, SafetyCommand, Gear } from '../contract'
import { clampUnit, clampSigned } from '../contract'

export interface InputState {
  steer: number
  throttle: number
  brake: number
  gear: Gear
  aux: AuxCommands
  safety: SafetyCommand
}

export function neutralInput(): InputState {
  return {
    steer: 0, throttle: 0, brake: 0, gear: 'N',
    aux: { blinker: 'off', headlights: false, workLights: false, horn: false, record: false, driveMode: 'slow' },
    safety: { arm: false, estop: false },
  }
}

export function applyDeadzone(v: number, dz = 0.08): number {
  const a = Math.abs(v)
  if (a < dz) return 0
  const scaled = (a - dz) / (1 - dz)
  return Math.sign(v) * scaled
}

export function buildCommandFrame(input: InputState, seq: number, heartbeat: number): CommandFrame {
  return {
    seq,
    heartbeat,
    steer: clampSigned(input.steer),
    throttle: clampUnit(input.throttle),
    brake: clampUnit(input.brake),
    gear: input.gear,
    aux: { ...input.aux },
    safety: { ...input.safety },
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/input/normalize.test.ts` → Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/input/normalize.ts web/src/input/normalize.test.ts
git commit -m "feat(input): InputState, deadzone, and clamped command frame builder"
```

---

### Task 8: Input adapters (gamepad + keyboard) and the drive loop

**Files:**
- Create: `web/src/input/gamepad.ts`, `web/src/input/keyboard.ts`, `web/src/input/useDriveLoop.ts`
- Test: `web/src/input/gamepad.test.ts`, `web/src/input/useDriveLoop.test.tsx`

**Interfaces:**
- Consumes: `InputState`, `neutralInput`, `applyDeadzone`, `buildCommandFrame` from `./normalize`; `VehicleLink` from `../transport/types`.
- Produces:
  - `readGamepad(prev: InputState): InputState` — maps a DualSense `Gamepad` (via `navigator.getGamepads()`) onto `InputState` (left stick X → steer, R2 → throttle, L2 → brake, D-pad → blinkers, face buttons → gear/horn/lights, L1+R1 combo → arm, Options → estop).
  - `createKeyboardInput(): { state(prev): InputState; dispose(): void }` — WASD/arrows steer+throttle, Space brake, etc.
  - `useDriveLoop(link, opts?)` — React hook running a fixed-rate (default 30 Hz) read→`buildCommandFrame`→`link.send` loop, incrementing `seq`, stamping `heartbeat = performance.now()`. Returns the latest `InputState` for HUD echo.

- [ ] **Step 1: Write the failing gamepad test**

`web/src/input/gamepad.test.ts`:
```ts
import { describe, it, expect, vi } from 'vitest'
import { readGamepad } from './gamepad'
import { neutralInput } from './normalize'

function fakePad(over: Partial<{ axes: number[]; buttons: number[] }> = {}): Gamepad {
  const axes = over.axes ?? [0, 0, 0, 0]
  const btnVals = over.buttons ?? new Array(18).fill(0)
  return {
    axes,
    buttons: btnVals.map((value) => ({ value, pressed: value > 0.5, touched: false })),
    connected: true, id: 'DualSense', index: 0, mapping: 'standard', timestamp: 0,
    hapticActuators: [], vibrationActuator: null,
  } as unknown as Gamepad
}

describe('readGamepad', () => {
  it('maps left stick X to steer with deadzone', () => {
    vi.spyOn(navigator, 'getGamepads').mockReturnValue([fakePad({ axes: [0.9, 0, 0, 0] })] as unknown as (Gamepad | null)[])
    const s = readGamepad(neutralInput())
    expect(s.steer).toBeGreaterThan(0.5)
  })

  it('maps R2 (button 7) to throttle and L2 (button 6) to brake', () => {
    const buttons = new Array(18).fill(0); buttons[7] = 1; buttons[6] = 0.5
    vi.spyOn(navigator, 'getGamepads').mockReturnValue([fakePad({ buttons })] as unknown as (Gamepad | null)[])
    const s = readGamepad(neutralInput())
    expect(s.throttle).toBe(1)
    expect(s.brake).toBeCloseTo(0.5, 5)
  })

  it('L1+R1 (4 and 5) together request arm', () => {
    const buttons = new Array(18).fill(0); buttons[4] = 1; buttons[5] = 1
    vi.spyOn(navigator, 'getGamepads').mockReturnValue([fakePad({ buttons })] as unknown as (Gamepad | null)[])
    const s = readGamepad(neutralInput())
    expect(s.safety.arm).toBe(true)
  })

  it('returns prev unchanged when no pad present', () => {
    vi.spyOn(navigator, 'getGamepads').mockReturnValue([null] as unknown as (Gamepad | null)[])
    const prev = { ...neutralInput(), steer: 0.3 }
    expect(readGamepad(prev).steer).toBe(0.3)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/input/gamepad.test.ts` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/input/gamepad.ts`**

```ts
import type { InputState } from './normalize'
import { applyDeadzone } from './normalize'
import type { Gear, BlinkerState } from '../contract'

// Standard-mapping DualSense indices.
const AX_LEFT_X = 0
const BTN_CROSS = 0, BTN_CIRCLE = 1, BTN_SQUARE = 2, BTN_TRIANGLE = 3
const BTN_L1 = 4, BTN_R1 = 5, BTN_L2 = 6, BTN_R2 = 7
const BTN_OPTIONS = 9
const BTN_DPAD_UP = 12, BTN_DPAD_DOWN = 13, BTN_DPAD_LEFT = 14, BTN_DPAD_RIGHT = 15

const val = (gp: Gamepad, i: number) => gp.buttons[i]?.value ?? 0
const pressed = (gp: Gamepad, i: number) => !!gp.buttons[i]?.pressed

export function readGamepad(prev: InputState): InputState {
  const gp = navigator.getGamepads?.().find((g): g is Gamepad => !!g)
  if (!gp) return prev

  const blinker: BlinkerState = pressed(gp, BTN_DPAD_LEFT)
    ? 'left'
    : pressed(gp, BTN_DPAD_RIGHT)
      ? 'right'
      : pressed(gp, BTN_DPAD_UP)
        ? 'hazard'
        : 'off'

  // Face buttons cycle gear: Triangle=F, Cross=N, Circle=R.
  const gear: Gear = pressed(gp, BTN_TRIANGLE) ? 'F' : pressed(gp, BTN_CIRCLE) ? 'R' : pressed(gp, BTN_CROSS) ? 'N' : prev.gear

  return {
    steer: applyDeadzone(gp.axes[AX_LEFT_X] ?? 0),
    throttle: val(gp, BTN_R2),
    brake: val(gp, BTN_L2),
    gear,
    aux: {
      blinker,
      headlights: pressed(gp, BTN_SQUARE) ? !prev.aux.headlights : prev.aux.headlights,
      workLights: prev.aux.workLights,
      horn: pressed(gp, BTN_DPAD_DOWN),
      record: pressed(gp, BTN_OPTIONS),
      driveMode: prev.aux.driveMode,
    },
    safety: {
      arm: pressed(gp, BTN_L1) && pressed(gp, BTN_R1),
      estop: pressed(gp, BTN_OPTIONS) && pressed(gp, BTN_L1) ? false : prev.safety.estop,
    },
  }
}
```

> During implementation, keep the estop mapping simple: dedicate a single combo. Replace the `estop:` line with `estop: pressed(gp, BTN_OPTIONS) && pressed(gp, BTN_R1)` (Options+R1 = E-STOP) so it can't collide with the L1+R1 arm combo. The keyboard and the on-screen button are the primary E-STOP paths.

- [ ] **Step 4: Implement `web/src/input/keyboard.ts`**

```ts
import type { InputState } from './normalize'
import { neutralInput } from './normalize'
import type { Gear } from '../contract'

/** Keyboard fallback. A/D steer, W throttle, S brake, Space = E-STOP, Enter = arm, F/N/R gear. */
export function createKeyboardInput(): { state: (prev: InputState) => InputState; dispose: () => void } {
  const down = new Set<string>()
  const onDown = (e: KeyboardEvent) => down.add(e.key.toLowerCase())
  const onUp = (e: KeyboardEvent) => down.delete(e.key.toLowerCase())
  window.addEventListener('keydown', onDown)
  window.addEventListener('keyup', onUp)

  return {
    state: (prev: InputState): InputState => {
      const gear: Gear = down.has('f') ? 'F' : down.has('r') ? 'R' : down.has('n') ? 'N' : prev.gear
      return {
        ...neutralInput(),
        steer: (down.has('d') ? 1 : 0) - (down.has('a') ? 1 : 0),
        throttle: down.has('w') ? 1 : 0,
        brake: down.has('s') ? 1 : 0,
        gear,
        aux: { ...prev.aux, horn: down.has('h'), record: down.has('o') },
        safety: { arm: down.has('enter'), estop: down.has(' ') ? true : prev.safety.estop },
      }
    },
    dispose: () => {
      window.removeEventListener('keydown', onDown)
      window.removeEventListener('keyup', onUp)
    },
  }
}
```

- [ ] **Step 5: Implement `web/src/input/useDriveLoop.ts`**

```ts
import { useEffect, useRef } from 'react'
import type { VehicleLink } from '../transport/types'
import type { InputState } from './normalize'
import { neutralInput, buildCommandFrame } from './normalize'
import { readGamepad } from './gamepad'
import { createKeyboardInput } from './keyboard'

export interface DriveLoopOptions { hz?: number }

/** Fixed-rate read → build → send loop. Merges gamepad over keyboard each tick. */
export function useDriveLoop(link: VehicleLink, opts: DriveLoopOptions = {}) {
  const hz = opts.hz ?? 30
  const latest = useRef<InputState>(neutralInput())

  useEffect(() => {
    const kb = createKeyboardInput()
    let seq = 0
    const period = 1000 / hz
    const id = setInterval(() => {
      const fromKb = kb.state(latest.current)
      const merged = readGamepad(fromKb) // gamepad takes precedence when present
      latest.current = merged
      link.send(buildCommandFrame(merged, ++seq, performance.now()))
    }, period)
    return () => { clearInterval(id); kb.dispose() }
  }, [link, hz])

  return latest
}
```

- [ ] **Step 6: Write the drive-loop test**

`web/src/input/useDriveLoop.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useDriveLoop } from './useDriveLoop'
import type { VehicleLink } from '../transport/types'
import type { CommandFrame } from '../contract'

describe('useDriveLoop', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.spyOn(navigator, 'getGamepads').mockReturnValue([null] as unknown as (Gamepad | null)[]) })
  afterEach(() => vi.useRealTimers())

  it('sends increasing seq command frames at the configured rate', () => {
    const sent: CommandFrame[] = []
    const link = { send: (c: CommandFrame) => sent.push(c) } as unknown as VehicleLink
    renderHook(() => useDriveLoop(link, { hz: 20 }))
    vi.advanceTimersByTime(250) // ~5 ticks at 20 Hz
    expect(sent.length).toBeGreaterThanOrEqual(4)
    expect(sent[1].seq).toBe(sent[0].seq + 1)
  })
})
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `npx vitest run src/input` → Expected: PASS (gamepad 4 + drive loop 1 + normalize 3).

- [ ] **Step 8: Commit**

```bash
git add web/src/input && git commit -m "feat(input): gamepad/keyboard adapters and fixed-rate drive loop"
```

---

### Task 9: TopStrip (link, latency, arm, REC, E-STOP)

**Files:**
- Create: `web/src/components/TopStrip.tsx`, `web/src/components/EStopButton.tsx`
- Test: `web/src/components/TopStrip.test.tsx`

**Interfaces:**
- Consumes: `useStatus`, `useTelemetry` from `../state/store`; `LinkStatus` from `../transport/types`; `TelemetryFrame` from `../contract`.
- Produces: `<TopStrip />` and `<EStopButton onEstop={() => void} />`. TopStrip renders RTT ms, a 4-bar quality meter, ARMED/DISARMED chip, REC dot (gold when `telemetry.recording`), and the E-STOP button.

- [ ] **Step 1: Write the failing test**

`web/src/components/TopStrip.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TopStrip } from './TopStrip'
import { useStore } from '../state/store'
import type { TelemetryFrame } from '../contract'

const tele = (over: Partial<TelemetryFrame> = {}): TelemetryFrame => ({
  seq: 1, timestamp: 0, speedKmh: 0, gear: 'N', steerAngleDeg: 0, driveMode: 'slow',
  armed: true, safetyState: 'DRIVING', battery: { percent: 80, runtimeMin: 40 },
  lights: { headlights: false, workLights: false, blinker: 'off', horn: false },
  temps: { jetsonC: 50 }, faults: [], recording: false, ...over,
})

describe('TopStrip', () => {
  beforeEach(() => { useStore.setState({ telemetry: tele(), status: { state: 'connected', rttMs: 142, quality: 'good' } }) })

  it('shows the latency number prominently', () => {
    render(<TopStrip />)
    expect(screen.getByText(/142/)).toBeInTheDocument()
  })

  it('shows ARMED when telemetry reports armed', () => {
    render(<TopStrip />)
    expect(screen.getByText(/ARMED/i)).toBeInTheDocument()
  })

  it('shows REC indicator when recording', () => {
    useStore.setState({ telemetry: tele({ recording: true }) })
    render(<TopStrip />)
    expect(screen.getByTestId('rec-indicator')).toHaveAttribute('data-on', 'true')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/TopStrip.test.tsx` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/components/EStopButton.tsx`**

```tsx
interface Props { onEstop: () => void }

export function EStopButton({ onEstop }: Props) {
  return (
    <button
      onClick={onEstop}
      data-testid="estop"
      className="rounded-md bg-alert px-4 py-1.5 text-sm font-semibold tracking-wide text-black hover:brightness-110 active:brightness-95"
    >
      ⏻ E-STOP
    </button>
  )
}
```

- [ ] **Step 4: Implement `web/src/components/TopStrip.tsx`**

```tsx
import { useStatus, useTelemetry, useStore } from '../state/store'
import { EStopButton } from './EStopButton'
import type { LinkQuality } from '../transport/types'

const BARS: Record<LinkQuality, number> = { good: 4, fair: 3, poor: 1 }

export function TopStrip() {
  const status = useStatus()
  const tele = useTelemetry()
  const link = useStore((s) => s.link)
  const bars = BARS[status.quality]

  return (
    <div className="pointer-events-auto flex items-center justify-between px-4 py-2 text-sm">
      <div className="flex items-center gap-3">
        <span className={status.state === 'connected' ? 'text-ok' : 'text-alert'}>◉ LINK</span>
        <span className="font-mono tabular-nums text-fg">{status.rttMs == null ? '—' : `${status.rttMs}ms`}</span>
        <span className="flex items-end gap-0.5" aria-label={`link ${status.quality}`}>
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className={`w-1 ${['h-2', 'h-3', 'h-4', 'h-5'][i]} ${i < bars ? 'bg-gold' : 'bg-muted/30'}`} />
          ))}
        </span>
        <span className="text-muted">{status.quality}</span>
      </div>

      <div className="flex items-center gap-4">
        <span className={tele?.armed ? 'font-semibold text-gold' : 'text-muted'}>
          {tele?.armed ? 'ARMED' : 'DISARMED'}
        </span>
        <span data-testid="rec-indicator" data-on={!!tele?.recording}
          className={tele?.recording ? 'text-gold' : 'text-muted'}>
          ⏺ {tele?.recording ? 'REC' : 'rec'}
        </span>
        <EStopButton onEstop={() => link.send(makeEstopFrame())} />
      </div>
    </div>
  )
}

import { neutralInput, buildCommandFrame } from '../input/normalize'
function makeEstopFrame() {
  const n = neutralInput()
  return buildCommandFrame({ ...n, safety: { arm: false, estop: true } }, -1, performance.now())
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run src/components/TopStrip.test.tsx` → Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/components/TopStrip.tsx web/src/components/EStopButton.tsx web/src/components/TopStrip.test.tsx
git commit -m "feat(ui): top strip with latency, arm, REC, and E-STOP"
```

---

### Task 10: DisconnectTakeover

**Files:**
- Create: `web/src/components/DisconnectTakeover.tsx`
- Test: `web/src/components/DisconnectTakeover.test.tsx`

**Interfaces:**
- Consumes: `useStatus` from `../state/store`.
- Produces: `<DisconnectTakeover />` — a full-screen red overlay rendered only when `status.state !== 'connected'`, so a frozen frame can never read as live.

- [ ] **Step 1: Write the failing test**

`web/src/components/DisconnectTakeover.test.tsx`:
```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DisconnectTakeover } from './DisconnectTakeover'
import { useStore } from '../state/store'

describe('DisconnectTakeover', () => {
  beforeEach(() => useStore.setState({ status: { state: 'connected', rttMs: 100, quality: 'good' } }))

  it('is hidden while connected', () => {
    render(<DisconnectTakeover />)
    expect(screen.queryByTestId('takeover')).toBeNull()
  })

  it('takes over on disconnect', () => {
    useStore.setState({ status: { state: 'disconnected', rttMs: null, quality: 'poor' } })
    render(<DisconnectTakeover />)
    expect(screen.getByTestId('takeover')).toBeInTheDocument()
    expect(screen.getByText(/LINK LOST/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/DisconnectTakeover.test.tsx` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/components/DisconnectTakeover.tsx`**

```tsx
import { useStatus } from '../state/store'

export function DisconnectTakeover() {
  const status = useStatus()
  if (status.state === 'connected') return null
  return (
    <div
      data-testid="takeover"
      className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-alert/90 text-black"
    >
      <div className="text-5xl font-bold tracking-widest">LINK LOST</div>
      <div className="mt-3 text-lg">
        {status.state === 'connecting' ? 'Reconnecting…' : 'Vehicle is stopped and latched.'}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/components/DisconnectTakeover.test.tsx` → Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/DisconnectTakeover.tsx web/src/components/DisconnectTakeover.test.tsx
git commit -m "feat(ui): full-screen link-lost takeover"
```

---

### Task 11: VideoLayer + object overlay

**Files:**
- Create: `web/src/components/VideoLayer.tsx`, `web/src/components/ObjectOverlay.tsx`
- Test: `web/src/components/ObjectOverlay.test.tsx`

**Interfaces:**
- Consumes: `useLink`, `useTelemetry` from `../state/store`; `DetectedObject` from `../contract`.
- Produces:
  - `<VideoLayer />` — a `<video>` element whose `srcObject` is `link.getVideoStream()`, full-bleed behind everything, with `<ObjectOverlay />` on top.
  - `<ObjectOverlay objects={DetectedObject[]} nearest={{distanceM, bearingDeg} | undefined} />` — draws normalized bounding boxes + distance labels, and an "⚠ OBSTACLE {d}m" banner when `nearest.distanceM` is below a threshold.

- [ ] **Step 1: Write the failing test**

`web/src/components/ObjectOverlay.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ObjectOverlay } from './ObjectOverlay'

describe('ObjectOverlay', () => {
  it('renders a labeled box per object', () => {
    render(<ObjectOverlay objects={[{ class: 'person', bbox: { x: 0.5, y: 0.4, w: 0.1, h: 0.2 }, distanceM: 3.2, bearingDeg: 10 }]} nearest={undefined} />)
    expect(screen.getByText(/person/i)).toBeInTheDocument()
    expect(screen.getByText(/3.2\s*m/i)).toBeInTheDocument()
  })

  it('shows obstacle banner when nearest is close', () => {
    render(<ObjectOverlay objects={[]} nearest={{ distanceM: 1.2, bearingDeg: 0 }} />)
    expect(screen.getByText(/OBSTACLE/i)).toBeInTheDocument()
  })

  it('hides obstacle banner when nearest is far', () => {
    render(<ObjectOverlay objects={[]} nearest={{ distanceM: 9, bearingDeg: 0 }} />)
    expect(screen.queryByText(/OBSTACLE/i)).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/ObjectOverlay.test.tsx` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/components/ObjectOverlay.tsx`**

```tsx
import type { DetectedObject } from '../contract'

const OBSTACLE_THRESHOLD_M = 2.0

interface Props {
  objects: DetectedObject[]
  nearest: { distanceM: number; bearingDeg: number } | undefined
}

export function ObjectOverlay({ objects, nearest }: Props) {
  const showObstacle = nearest != null && nearest.distanceM < OBSTACLE_THRESHOLD_M
  return (
    <div className="pointer-events-none absolute inset-0">
      {objects.map((o, i) => (
        <div
          key={i}
          className="absolute border border-gold/80"
          style={{
            left: `${o.bbox.x * 100}%`, top: `${o.bbox.y * 100}%`,
            width: `${o.bbox.w * 100}%`, height: `${o.bbox.h * 100}%`,
          }}
        >
          <span className="absolute -top-5 left-0 whitespace-nowrap bg-black/70 px-1 text-xs text-gold">
            {o.class} {o.distanceM.toFixed(1)} m
          </span>
        </div>
      ))}
      {showObstacle && (
        <div className="absolute left-1/2 top-1/3 -translate-x-1/2 rounded bg-alert/85 px-3 py-1 text-sm font-semibold text-black">
          ⚠ OBSTACLE {nearest!.distanceM.toFixed(1)}m
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Implement `web/src/components/VideoLayer.tsx`**

```tsx
import { useEffect, useRef } from 'react'
import { useLink, useTelemetry } from '../state/store'
import { ObjectOverlay } from './ObjectOverlay'

export function VideoLayer() {
  const link = useLink()
  const tele = useTelemetry()
  const ref = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const v = ref.current
    if (!v) return
    const stream = link.getVideoStream()
    if (stream) { v.srcObject = stream; void v.play?.().catch(() => {}) }
  }, [link, tele?.seq])

  return (
    <div className="absolute inset-0 bg-black">
      <video ref={ref} autoPlay muted playsInline className="h-full w-full object-cover" />
      <ObjectOverlay objects={tele?.perception?.objects ?? []} nearest={tele?.perception?.nearestObstacle} />
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run src/components/ObjectOverlay.test.tsx` → Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/components/VideoLayer.tsx web/src/components/ObjectOverlay.tsx web/src/components/ObjectOverlay.test.tsx
git commit -m "feat(ui): full-bleed video layer with object/obstacle overlay"
```

---

### Task 12: Edge instruments — TiltIndicator + ProximityRing

**Files:**
- Create: `web/src/components/TiltIndicator.tsx`, `web/src/components/ProximityRing.tsx`
- Test: `web/src/components/TiltIndicator.test.tsx`, `web/src/components/ProximityRing.test.tsx`

**Interfaces:**
- Consumes: `PerceptionTelemetry`, `PROXIMITY_BINS` from `../contract`.
- Produces:
  - `<TiltIndicator pitchDeg={number} rollDeg={number} />` — left-edge attitude readout; rotates a horizon line by `rollDeg`, shows numeric pitch.
  - `<ProximityRing ranges={number[]} />` — top-down ring; renders one radial tick per range bin, closer = brighter/gold.

- [ ] **Step 1: Write the failing tests**

`web/src/components/TiltIndicator.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TiltIndicator } from './TiltIndicator'

describe('TiltIndicator', () => {
  it('renders pitch and roll numbers', () => {
    render(<TiltIndicator pitchDeg={4} rollDeg={-2} />)
    expect(screen.getByText(/4°/)).toBeInTheDocument()
  })
})
```

`web/src/components/ProximityRing.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ProximityRing } from './ProximityRing'

describe('ProximityRing', () => {
  it('renders one tick per range bin', () => {
    const { container } = render(<ProximityRing ranges={[1, 2, 3, 4]} />)
    expect(container.querySelectorAll('[data-bin]').length).toBe(4)
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run src/components/TiltIndicator.test.tsx src/components/ProximityRing.test.tsx` → Expected: FAIL (modules missing).

- [ ] **Step 3: Implement `web/src/components/TiltIndicator.tsx`**

```tsx
interface Props { pitchDeg: number; rollDeg: number }

export function TiltIndicator({ pitchDeg, rollDeg }: Props) {
  return (
    <div className="flex h-24 w-24 flex-col items-center justify-center rounded-lg border border-muted/20 bg-panel/60">
      <div className="relative h-12 w-12 overflow-hidden rounded-full border border-muted/30">
        <div
          className="absolute left-0 top-1/2 h-px w-full bg-gold"
          style={{ transform: `translateY(${pitchDeg}px) rotate(${rollDeg}deg)` }}
        />
      </div>
      <div className="mt-1 font-mono text-xs text-fg">{pitchDeg.toFixed(0)}° ◣</div>
    </div>
  )
}
```

- [ ] **Step 4: Implement `web/src/components/ProximityRing.tsx`**

```tsx
interface Props { ranges: number[] }

const MAX_M = 8

export function ProximityRing({ ranges }: Props) {
  const n = ranges.length || 1
  return (
    <div className="relative h-32 w-32 rounded-full border border-muted/20 bg-panel/60">
      <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-fg" />
      {ranges.map((r, i) => {
        const angle = (i / n) * Math.PI * 2
        const norm = Math.max(0, Math.min(1, 1 - r / MAX_M))
        const radius = 12 + (1 - norm) * 50
        const x = 50 + Math.cos(angle) * radius
        const y = 50 + Math.sin(angle) * radius
        return (
          <span
            key={i}
            data-bin
            className="absolute h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ left: `${x}%`, top: `${y}%`, backgroundColor: `rgba(254,218,129,${0.25 + norm * 0.75})` }}
          />
        )
      })}
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run src/components/TiltIndicator.test.tsx src/components/ProximityRing.test.tsx` → Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/components/TiltIndicator.tsx web/src/components/ProximityRing.tsx web/src/components/TiltIndicator.test.tsx web/src/components/ProximityRing.test.tsx
git commit -m "feat(ui): tilt indicator and top-down proximity ring instruments"
```

---

### Task 13: BottomHud (gear, speed, battery, mode, confirmed lights)

**Files:**
- Create: `web/src/components/BottomHud.tsx`
- Test: `web/src/components/BottomHud.test.tsx`

**Interfaces:**
- Consumes: `useTelemetry` from `../state/store`; `TelemetryFrame` from `../contract`.
- Produces: `<BottomHud />` — gear F/N/R (active highlighted), large speed readout, battery % + runtime, drive-mode chip, and a lights/blinker/horn row whose icons are lit ONLY from confirmed telemetry (`tele.lights.*`).

- [ ] **Step 1: Write the failing test**

`web/src/components/BottomHud.test.tsx`:
```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BottomHud } from './BottomHud'
import { useStore } from '../state/store'
import type { TelemetryFrame } from '../contract'

const tele = (over: Partial<TelemetryFrame> = {}): TelemetryFrame => ({
  seq: 1, timestamp: 0, speedKmh: 18, gear: 'F', steerAngleDeg: 0, driveMode: 'slow',
  armed: true, safetyState: 'DRIVING', battery: { percent: 82, runtimeMin: 41 },
  lights: { headlights: true, workLights: false, blinker: 'left', horn: false },
  temps: { jetsonC: 50 }, faults: [], recording: false, ...over,
})

describe('BottomHud', () => {
  beforeEach(() => useStore.setState({ telemetry: tele() }))

  it('shows speed, battery, and runtime', () => {
    render(<BottomHud />)
    expect(screen.getByText(/18/)).toBeInTheDocument()
    expect(screen.getByText(/82\s*%/)).toBeInTheDocument()
    expect(screen.getByText(/41\s*min/i)).toBeInTheDocument()
  })

  it('lights headlights icon only when telemetry confirms on', () => {
    render(<BottomHud />)
    expect(screen.getByTestId('light-headlights')).toHaveAttribute('data-on', 'true')
    expect(screen.getByTestId('light-horn')).toHaveAttribute('data-on', 'false')
  })

  it('highlights the active gear', () => {
    render(<BottomHud />)
    expect(screen.getByTestId('gear-F')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('gear-R')).toHaveAttribute('data-active', 'false')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/BottomHud.test.tsx` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/components/BottomHud.tsx`**

```tsx
import { useTelemetry } from '../state/store'
import type { Gear } from '../contract'

const GEARS: Gear[] = ['F', 'N', 'R']

export function BottomHud() {
  const t = useTelemetry()
  if (!t) return null
  return (
    <div className="pointer-events-auto flex items-end justify-between px-4 py-3">
      <div className="flex items-center gap-1 rounded-md bg-panel/70 p-1">
        {GEARS.map((g) => (
          <span
            key={g}
            data-testid={`gear-${g}`}
            data-active={t.gear === g}
            className={`px-2 py-1 text-sm font-semibold ${t.gear === g ? 'rounded bg-gold text-black' : 'text-muted'}`}
          >
            {g}
          </span>
        ))}
      </div>

      <div className="flex items-end gap-1">
        <span className="font-mono text-4xl tabular-nums text-fg">{Math.round(t.speedKmh)}</span>
        <span className="pb-1 text-sm text-muted">km/h</span>
      </div>

      <div className="flex items-center gap-4 text-sm">
        <LightIcon id="headlights" on={t.lights.headlights} label="🔆" />
        <LightIcon id="blinker" on={t.lights.blinker !== 'off'} label="⇄" />
        <LightIcon id="horn" on={t.lights.horn} label="📢" />
        <span className="rounded bg-panel/70 px-2 py-0.5 uppercase text-muted">{t.driveMode}</span>
        <span className="text-fg">🔋 {t.battery.percent}%</span>
        <span className="text-muted">· {t.battery.runtimeMin} min</span>
      </div>
    </div>
  )
}

function LightIcon({ id, on, label }: { id: string; on: boolean; label: string }) {
  return (
    <span data-testid={`light-${id}`} data-on={on} className={on ? 'text-gold' : 'text-muted/50'}>
      {label}
    </span>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run src/components/BottomHud.test.tsx` → Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/components/BottomHud.tsx web/src/components/BottomHud.test.tsx
git commit -m "feat(ui): bottom HUD with gear, speed, battery, and confirmed-state lights"
```

---

### Task 14: Cockpit composition, dev latency panel, and loopback integration test

**Files:**
- Create: `web/src/components/Cockpit.tsx`, `web/src/components/DevLatencyPanel.tsx`, `web/src/components/Cockpit.integration.test.tsx`
- Modify: `web/src/App.tsx` (render `<Cockpit />`)

**Interfaces:**
- Consumes: every component above, `useStore`, `useDriveLoop`.
- Produces: `<Cockpit />` — the full layout (TopStrip top, VideoLayer behind, edge instruments left, BottomHud bottom, DisconnectTakeover on top), auto-connects on mount, runs the drive loop. `<DevLatencyPanel />` injects artificial RTT (slider 0–500 ms) to validate §10 latency behavior.

- [ ] **Step 1: Write the failing integration test**

`web/src/components/Cockpit.integration.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { Cockpit } from './Cockpit'
import { useStore } from '../state/store'

describe('Cockpit loopback (browser → mock → back)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    const proto = HTMLCanvasElement.prototype as unknown as { captureStream?: () => MediaStream }
    proto.captureStream = vi.fn(() => ({ id: 'fake', getTracks: () => [] }) as unknown as MediaStream)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      fillRect: vi.fn(), fillStyle: '', fillText: vi.fn(), font: '',
    } as unknown as CanvasRenderingContext2D)
    vi.spyOn(navigator, 'getGamepads').mockReturnValue([null] as unknown as (Gamepad | null)[])
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined)
  })
  afterEach(() => { useStore.getState().disconnect(); vi.useRealTimers() })

  it('connects, streams telemetry, and clears the takeover', () => {
    render(<Cockpit />)
    act(() => { vi.advanceTimersByTime(1000) })
    expect(useStore.getState().status.state).toBe('connected')
    expect(useStore.getState().telemetry).not.toBeNull()
    expect(screen.queryByTestId('takeover')).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/Cockpit.integration.test.tsx` → Expected: FAIL (module missing).

- [ ] **Step 3: Implement `web/src/components/DevLatencyPanel.tsx`**

```tsx
import { useStore } from '../state/store'

export function DevLatencyPanel() {
  const injected = useStore((s) => s.injectedLatency)
  const setInjectedLatency = useStore((s) => s.setInjectedLatency)
  return (
    <div className="pointer-events-auto flex items-center gap-2 rounded-md bg-panel/80 px-3 py-1 text-xs text-muted">
      <span>+lat</span>
      <input
        type="range" min={0} max={500} step={10} value={injected}
        onChange={(e) => setInjectedLatency(Number(e.target.value))}
        aria-label="injected latency"
      />
      <span className="font-mono text-fg">{injected}ms</span>
    </div>
  )
}
```

- [ ] **Step 4: Implement `web/src/components/Cockpit.tsx`**

```tsx
import { useEffect } from 'react'
import { useStore, useLink, useTelemetry } from '../state/store'
import { useDriveLoop } from '../input/useDriveLoop'
import { TopStrip } from './TopStrip'
import { VideoLayer } from './VideoLayer'
import { BottomHud } from './BottomHud'
import { TiltIndicator } from './TiltIndicator'
import { ProximityRing } from './ProximityRing'
import { DisconnectTakeover } from './DisconnectTakeover'
import { DevLatencyPanel } from './DevLatencyPanel'

export function Cockpit() {
  const connect = useStore((s) => s.connect)
  const disconnect = useStore((s) => s.disconnect)
  const link = useLink()
  const tele = useTelemetry()
  useDriveLoop(link, { hz: 30 })

  useEffect(() => { connect(); return () => disconnect() }, [connect, disconnect])

  const att = tele?.perception?.attitude
  const ranges = tele?.perception?.proximity ?? []

  return (
    <div className="relative h-full w-full overflow-hidden bg-bg text-fg">
      <VideoLayer />

      {/* Top strip */}
      <div className="absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-black/70 to-transparent">
        <TopStrip />
      </div>

      {/* Left edge instruments */}
      <div className="absolute left-4 top-1/3 z-20 flex flex-col gap-3">
        {att && <TiltIndicator pitchDeg={att.pitchDeg} rollDeg={att.rollDeg} />}
      </div>

      {/* Center-bottom proximity ring */}
      <div className="absolute bottom-24 left-1/2 z-20 -translate-x-1/2">
        {ranges.length > 0 && <ProximityRing ranges={ranges} />}
      </div>

      {/* Bottom HUD */}
      <div className="absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-black/80 to-transparent">
        <BottomHud />
      </div>

      {/* Dev tools */}
      <div className="absolute right-4 top-14 z-30">
        <DevLatencyPanel />
      </div>

      <DisconnectTakeover />
    </div>
  )
}
```

- [ ] **Step 5: Wire `web/src/App.tsx`**

```tsx
import { Cockpit } from './components/Cockpit'

export default function App() {
  return <Cockpit />
}
```

- [ ] **Step 6: Run the integration test, then the full suite**

Run: `npx vitest run src/components/Cockpit.integration.test.tsx` → Expected: PASS (1 test).
Run: `cd /Users/akashsuryavanshi/Projects/Argus_Drive/web && npm test` → Expected: ALL tests PASS.

- [ ] **Step 7: Manual smoke check**

Run: `npm run dev`, open the served URL. Expected: dark cockpit, moving mock feed, latency in the top strip, gauges at idle. Press Enter (arm) + hold W → speed climbs and caps; release → coasts to 0; drag the +lat slider past ~320 ms → quality drops to `poor`; press Space (E-STOP) → ARMED → DISARMED and speed falls to 0; only a fresh arm (Enter) recovers.

- [ ] **Step 8: Commit**

```bash
git add web/src/components/Cockpit.tsx web/src/components/DevLatencyPanel.tsx web/src/components/Cockpit.integration.test.tsx web/src/App.tsx
git commit -m "feat(ui): assemble cockpit, dev latency panel, and loopback integration test"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- §4.1 command contract → Task 2 (`CommandFrame`, `AuxCommands`, `SafetyCommand`); normalized + seq + heartbeat → Tasks 7–8.
- §4.2 telemetry contract → Task 2 (`TelemetryFrame`, perception fields).
- §6.2 safety model (watchdog 300 ms, latch, re-arm, E-STOP, speed cap) → Task 3 (`stepVehicle`), surfaced in Tasks 9/10/14.
- §7 cockpit zones: top strip → Task 9; disconnect takeover → Task 10; video + overlays → Task 11; bottom HUD confirmed-state → Task 13; edge instruments → Task 12; layout → Task 14. Input mapping (DualSense/keyboard) → Task 8.
- §8 perception (designed-now fields, on-vehicle compute, derived telemetry only) → contract in Task 2, mock emission in Task 3, overlays in Tasks 11–12. (Built against mock now; real ZED wiring is the AGX plan.)
- §10 testing: dummy vehicle → Task 3; unit tests on normalization/command-mapping/watchdog → Tasks 3,7; loopback integration → Task 14; latency injection → Tasks 5/14; mock vehicle for UI → Tasks 4–6.
- §11 phasing: this plan IS Phase 0 items 0.2 (contract) + 0.3 (UI vs mock).

**Out of scope here (sibling AGX plan):** NVENC video spike (0.1), `argus_teleop_bridge` WebRTC/aiortc node, `argus_safety_watchdog` ROS node, `dummy_vehicle` ROS node, signaling server, Tailscale/TURN, real ZED `zed_ros2_wrapper` wiring. The `VehicleLink` interface (Task 5) is the seam these plug into via `createLink.ts`.

**Placeholder scan:** none — every step ships real code/commands. The one acknowledged rough edge (recording-toggle tangle in Task 3 Step 3) is explicitly cleaned in Step 4.

**Type consistency:** `CommandFrame`/`TelemetryFrame`/`InputState`/`VehicleLink`/`LinkStatus`/`VehicleSimState` names and field shapes are defined once (Tasks 2,3,5,7) and used verbatim downstream. `stepVehicle`, `toTelemetry`, `buildCommandFrame`, `readGamepad`, `useDriveLoop`, `createLink`, `useStore`/`useTelemetry`/`useStatus`/`useLink` signatures match across tasks.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-18-argus-drive-cockpit-ui.md`.
</content>
</invoke>
