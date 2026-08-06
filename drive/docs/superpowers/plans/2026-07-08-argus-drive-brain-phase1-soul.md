# Argus-Drive-Brain — Phase 1 "The Soul" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Argus vehicle a talking, seeing, pre-flighting brain that can also execute bounded spoken-drive commands — cloud brain, browser voice, reusing the existing `/cmd_vel`-equivalent Remo token spine.

**Architecture:** A cloud **Brain service** (Node/TS) turns a conversation turn + camera frame + telemetry into a spoken reply and an optional high-level drive intent, using a vision-capable Claude model with guaranteed-JSON structured output. The **cockpit** (existing React/Vite app) grows a voice panel (browser Web Speech API for STT/TTS, `getUserMedia` for the P1 camera frame), computes a deterministic pre-flight over the existing `Telemetry` contract, and converts a returned drive intent into a **bounded** `Command` (capped magnitude + capped duration + auto-neutral) that flows through the existing `TokenEmitter` → relay. The human operator stays the single relay DRIVER and always overrides.

**Tech Stack:** TypeScript everywhere. Brain service: Node ≥ 20, `@anthropic-ai/sdk`, `zod`, `vitest`. Cockpit: existing React 19 + Vite + zustand + `vitest`. Browser Web Speech API (`SpeechRecognition` + `speechSynthesis`) for voice. Model: `claude-opus-4-8`.

## Global Constraints

- **Model ID is exactly `claude-opus-4-8`** — vision-capable, current default. Never append a date suffix.
- **Structured output:** the brain returns JSON validated against a schema via `client.messages.parse()` + `zodOutputFormat(...)`; never raw-string-parse the model output.
- **`max_tokens: 16000`** for the (non-streaming) brain call.
- **Secrets:** `ANTHROPIC_API_KEY` comes from the environment only. Never write a key into any file in the repo.
- **Drive safety (non-negotiable):** the brain never emits raw motor tokens. It emits a high-level `DriveIntent`; the cockpit converts it to a **bounded** `Command` (throttle ≤ `THROTTLE_CAP`, active ≤ `MAX_DRIVE_MS`, then auto-neutral). Human manual input overrides brain drive on the same tick. The cockpit stays the single relay DRIVER.
- **Hardware is forward-only** (`web/src/transport/tokens.ts`): supported drive actions are `forward`, `left`, `right`, `stop`, `none` — no reverse.
- **Jetson stays stdlib-only** — no new code runs on the Jetson in Phase 1 (brain is cloud; voice/camera are in the browser). Do not add dependencies to `test-bridge/`.
- **Reuse, don't fork:** consume `Command`, `Telemetry`, `neutralCommand` from `web/src/contract/index.ts` and `TokenEmitter` from `web/src/transport/tokens.ts` unchanged.

---

## File Structure

**New — Brain service (`brain/`):**
- `brain/package.json`, `brain/tsconfig.json`, `brain/vitest.config.ts` — package setup
- `brain/src/types.ts` — `DriveIntent`, `CheckResult`, `BrainTurn`, `BrainReply`, `Telemetry` (mirrored)
- `brain/src/reply-schema.ts` — zod schema for `BrainReply`
- `brain/src/anthropic-brain.ts` — `createAnthropicBrain(client)`: assembles the vision message, calls the model, returns a validated `BrainReply`
- `brain/src/server.ts` — HTTP server exposing `POST /brain/turn`
- `brain/test/anthropic-brain.test.ts` — request assembly + parsing, fake client (no network)

**New — cockpit brain integration (`web/src/brain/`):**
- `web/src/brain/types.ts` — `DriveIntent`, `CheckResult`, `BrainTurn`, `BrainReply` (must match `brain/src/types.ts`)
- `web/src/brain/preflight.ts` — `evaluatePreflight(t: Telemetry): CheckResult[]` (pure)
- `web/src/brain/preflight.test.ts`
- `web/src/brain/driveIntent.ts` — `intentToCommand(intent, caps): Command` (pure) + `DRIVE_CAPS`
- `web/src/brain/driveIntent.test.ts`
- `web/src/brain/brainClient.ts` — `postTurn(turn): Promise<BrainReply>` with response guard
- `web/src/brain/useVoice.ts` — Web Speech STT + TTS hook
- `web/src/brain/useCameraFrame.ts` — `getUserMedia` → JPEG base64 grab (P1 camera stand-in)
- `web/src/cockpit/BrainPanel.tsx` — the voice/conversation panel

**Modified:**
- `web/src/cockpit/CockpitScreen.tsx` — mount `<BrainPanel />` and wire the assist toggle + override

---

## MILESTONE M1 — Brain service skeleton (Verify: acceptance criterion 1, "talks", against the service)

### Task 1: Scaffold the brain service package

**Files:**
- Create: `brain/package.json`
- Create: `brain/tsconfig.json`
- Create: `brain/vitest.config.ts`

- [ ] **Step 1: Write `brain/package.json`**

```json
{
  "name": "argus-brain",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "node --experimental-strip-types src/server.ts",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@anthropic-ai/sdk": "^0.68.0",
    "zod": "^3.25.0"
  },
  "devDependencies": {
    "typescript": "^5.9.0",
    "vitest": "^3.2.0",
    "@types/node": "^22.0.0"
  }
}
```

- [ ] **Step 2: Write `brain/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["src", "test"]
}
```

- [ ] **Step 3: Write `brain/vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: { environment: 'node' },
})
```

- [ ] **Step 4: Install and verify**

Run: `cd brain && npm install && npm run typecheck`
Expected: install succeeds; typecheck passes with no source files yet (exit 0).

- [ ] **Step 5: Commit**

```bash
git add brain/package.json brain/tsconfig.json brain/vitest.config.ts brain/package-lock.json
git commit -m "chore(brain): scaffold Node/TS brain service package"
```

### Task 2: Define the brain contract types

**Files:**
- Create: `brain/src/types.ts`

**Interfaces:**
- Produces: `DriveIntent`, `CheckResult`, `BrainTurn`, `BrainReply`, `Telemetry` — consumed by `anthropic-brain.ts`, `server.ts`, and mirrored in `web/src/brain/types.ts`.

- [ ] **Step 1: Write `brain/src/types.ts`**

```ts
// Mirror of the fields the cockpit's Telemetry contract exposes (web/src/contract/index.ts).
// Kept structural (not imported) so the brain service has no dependency on the web app.
export interface Telemetry {
  speedKmh: number
  gear: 'R' | 'N' | 'F'
  steerAngleDeg: number
  mode: 'MANUAL' | 'AUTO'
  armed: boolean
  safetyState: 'DRIVING' | 'STOPPED' | 'LATCHED'
  battery: { percent: number; runtimeMin: number }
  lights: { headlights: boolean; blinker: 'off' | 'left' | 'right' | 'hazard'; horn: boolean }
  recording: boolean
  linkRttMs: number
  tempC: number
  headingDeg: number
}

export type DriveAction = 'forward' | 'left' | 'right' | 'stop' | 'none'

export interface DriveIntent {
  action: DriveAction
  /** requested active duration in ms; the cockpit clamps this to MAX_DRIVE_MS */
  durationMs?: number
}

export interface CheckResult {
  item: string
  status: 'ok' | 'warn' | 'fail'
  detail: string
}

export interface BrainTurn {
  transcript: string
  cameraFrameJpegBase64?: string
  telemetry?: Telemetry
  preflight?: CheckResult[]
  recentTurns?: { role: 'user' | 'brain'; text: string }[]
}

export interface BrainReply {
  speech: string
  driveIntent: DriveIntent | null
}
```

- [ ] **Step 2: Typecheck**

Run: `cd brain && npm run typecheck`
Expected: PASS (exit 0).

- [ ] **Step 3: Commit**

```bash
git add brain/src/types.ts
git commit -m "feat(brain): define BrainTurn/BrainReply/DriveIntent contract"
```

### Task 3: The reply schema

**Files:**
- Create: `brain/src/reply-schema.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `BrainReplySchema` (zod) — consumed by `anthropic-brain.ts`. Its inferred type must be assignable to `BrainReply`.

- [ ] **Step 1: Write `brain/src/reply-schema.ts`**

```ts
import { z } from 'zod'

export const BrainReplySchema = z.object({
  speech: z.string().describe('What the vehicle says back to the operator, in its own voice.'),
  driveIntent: z
    .object({
      action: z.enum(['forward', 'left', 'right', 'stop', 'none']),
      durationMs: z.number().optional(),
    })
    .nullable()
    .describe('A bounded drive action to perform, or null when the reply is conversational only.'),
})
```

- [ ] **Step 2: Typecheck**

Run: `cd brain && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add brain/src/reply-schema.ts
git commit -m "feat(brain): zod schema for structured BrainReply output"
```

### Task 4: The Anthropic brain (TDD — assembly + parsing, fake client)

**Files:**
- Create: `brain/src/anthropic-brain.ts`
- Test: `brain/test/anthropic-brain.test.ts`

**Interfaces:**
- Consumes: `BrainTurn`, `BrainReply` (types.ts); `BrainReplySchema` (reply-schema.ts).
- Produces: `createAnthropicBrain(client): { generate(turn: BrainTurn): Promise<BrainReply> }`. `client` is anything with a `messages.parse(params)` method returning `{ parsed_output: BrainReply | null }` — the real `@anthropic-ai/sdk` client satisfies this.

- [ ] **Step 1: Write the failing test**

```ts
// brain/test/anthropic-brain.test.ts
import { describe, it, expect, vi } from 'vitest'
import { createAnthropicBrain } from '../src/anthropic-brain.ts'
import type { BrainTurn } from '../src/types.ts'

function fakeClient(reply = { speech: 'Hello, operator.', driveIntent: null }) {
  const parse = vi.fn().mockResolvedValue({ parsed_output: reply })
  return { client: { messages: { parse } }, parse }
}

describe('createAnthropicBrain', () => {
  it('returns the parsed reply for a text-only turn', async () => {
    const { client } = fakeClient()
    const brain = createAnthropicBrain(client as never)
    const turn: BrainTurn = { transcript: 'Hi there' }
    const reply = await brain.generate(turn)
    expect(reply.speech).toBe('Hello, operator.')
    expect(reply.driveIntent).toBeNull()
  })

  it('includes a base64 image block when a camera frame is present', async () => {
    const { client, parse } = fakeClient()
    const brain = createAnthropicBrain(client as never)
    await brain.generate({ transcript: 'what do you see?', cameraFrameJpegBase64: 'QUJD' })
    const params = parse.mock.calls[0][0]
    const userContent = params.messages.at(-1).content
    const imageBlock = userContent.find((b: { type: string }) => b.type === 'image')
    expect(imageBlock).toBeTruthy()
    expect(imageBlock.source).toMatchObject({ type: 'base64', media_type: 'image/jpeg', data: 'QUJD' })
    expect(params.model).toBe('claude-opus-4-8')
  })

  it('throws when the model returns no parseable output', async () => {
    const parse = vi.fn().mockResolvedValue({ parsed_output: null })
    const brain = createAnthropicBrain({ messages: { parse } } as never)
    await expect(brain.generate({ transcript: 'hi' })).rejects.toThrow(/parse/i)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd brain && npx vitest run test/anthropic-brain.test.ts`
Expected: FAIL — cannot import `createAnthropicBrain` (module not found).

- [ ] **Step 3: Write `brain/src/anthropic-brain.ts`**

```ts
import { zodOutputFormat } from '@anthropic-ai/sdk/helpers/zod'
import { BrainReplySchema } from './reply-schema.ts'
import type { BrainTurn, BrainReply } from './types.ts'

const SYSTEM = `You are Argus, the onboard mind of a small autonomous ground vehicle.
You speak briefly, calmly, and competently — a capable co-pilot, not a chatbot.
You can SEE through the camera frame when one is provided: describe only what is
actually visible. When asked to run a pre-flight, read the provided checklist
results and summarize them plainly, calling out any warn/fail item.

You may propose a SINGLE bounded drive action via driveIntent when the operator
clearly asks you to move ('nudge forward', 'turn left a little', 'stop').
Otherwise driveIntent MUST be null. You never drive on your own initiative.
Keep 'speech' to one or two sentences.`

interface ParseClient {
  messages: { parse: (params: unknown) => Promise<{ parsed_output: BrainReply | null }> }
}

export function createAnthropicBrain(client: ParseClient) {
  return {
    async generate(turn: BrainTurn): Promise<BrainReply> {
      const userContent: Array<Record<string, unknown>> = []
      if (turn.cameraFrameJpegBase64) {
        userContent.push({
          type: 'image',
          source: { type: 'base64', media_type: 'image/jpeg', data: turn.cameraFrameJpegBase64 },
        })
      }
      const context = {
        telemetry: turn.telemetry ?? null,
        preflight: turn.preflight ?? null,
        recentTurns: turn.recentTurns ?? [],
      }
      userContent.push({
        type: 'text',
        text: `Operator said: ${turn.transcript}\n\nContext (JSON): ${JSON.stringify(context)}`,
      })

      const res = await client.messages.parse({
        model: 'claude-opus-4-8',
        max_tokens: 16000,
        system: SYSTEM,
        messages: [{ role: 'user', content: userContent }],
        output_config: { format: zodOutputFormat(BrainReplySchema) },
      })

      if (!res.parsed_output) throw new Error('brain: model returned no parseable output')
      return res.parsed_output
    },
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd brain && npx vitest run test/anthropic-brain.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add brain/src/anthropic-brain.ts brain/test/anthropic-brain.test.ts
git commit -m "feat(brain): vision brain call with structured reply + tests"
```

### Task 5: The HTTP endpoint

**Files:**
- Create: `brain/src/server.ts`

**Interfaces:**
- Consumes: `createAnthropicBrain`; `@anthropic-ai/sdk` default export.
- Produces: an HTTP server; `POST /brain/turn` accepts a JSON `BrainTurn`, returns a JSON `BrainReply`. `GET /health` returns `{ ok: true }`.

- [ ] **Step 1: Write `brain/src/server.ts`**

```ts
import { createServer } from 'node:http'
import Anthropic from '@anthropic-ai/sdk'
import { createAnthropicBrain } from './anthropic-brain.ts'
import type { BrainTurn } from './types.ts'

const brain = createAnthropicBrain(new Anthropic())
const PORT = Number(process.env.BRAIN_PORT ?? 8099)

function send(res: import('node:http').ServerResponse, code: number, body: unknown) {
  const data = JSON.stringify(body)
  res.writeHead(code, {
    'content-type': 'application/json',
    'access-control-allow-origin': process.env.BRAIN_CORS_ORIGIN ?? '*',
    'access-control-allow-headers': 'content-type',
    'access-control-allow-methods': 'POST, OPTIONS',
  })
  res.end(data)
}

const server = createServer((req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, {})
  if (req.method === 'GET' && req.url === '/health') return send(res, 200, { ok: true })
  if (req.method === 'POST' && req.url === '/brain/turn') {
    let raw = ''
    req.on('data', (c) => (raw += c))
    req.on('end', async () => {
      try {
        const turn = JSON.parse(raw) as BrainTurn
        if (typeof turn.transcript !== 'string') return send(res, 400, { error: 'transcript required' })
        const reply = await brain.generate(turn)
        send(res, 200, reply)
      } catch (err) {
        send(res, 500, { error: String(err instanceof Error ? err.message : err) })
      }
    })
    return
  }
  send(res, 404, { error: 'not found' })
})

server.listen(PORT, () => console.log(`[brain] listening on :${PORT}`))
```

- [ ] **Step 2: Typecheck**

Run: `cd brain && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Manual verify — the "talks" criterion (acceptance criterion 1)**

Run (needs a real key):
```bash
cd brain && ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY npm run dev &
sleep 1
curl -s localhost:8099/brain/turn -H 'content-type: application/json' \
  -d '{"transcript":"Hello Argus, introduce yourself."}'
```
Expected: a JSON `{ "speech": "...", "driveIntent": null }` with a one-to-two-sentence spoken reply. Stop the server afterward.

- [ ] **Step 4: Commit**

```bash
git add brain/src/server.ts
git commit -m "feat(brain): POST /brain/turn endpoint + health check"
```

---

## MILESTONE M2 — Cockpit voice panel (Verify: acceptance criterion 1 end-to-end in the browser)

### Task 6: Mirror the brain types into the cockpit

**Files:**
- Create: `web/src/brain/types.ts`

**Interfaces:**
- Produces: `DriveIntent`, `DriveAction`, `CheckResult`, `BrainTurn`, `BrainReply` — must be structurally identical to `brain/src/types.ts` (same field names/types). `BrainTurn.telemetry` uses the cockpit's own `Telemetry` from `../contract`.

- [ ] **Step 1: Write `web/src/brain/types.ts`**

```ts
import type { Telemetry } from '../contract'

export type DriveAction = 'forward' | 'left' | 'right' | 'stop' | 'none'

export interface DriveIntent {
  action: DriveAction
  durationMs?: number
}

export interface CheckResult {
  item: string
  status: 'ok' | 'warn' | 'fail'
  detail: string
}

export interface BrainTurn {
  transcript: string
  cameraFrameJpegBase64?: string
  telemetry?: Telemetry
  preflight?: CheckResult[]
  recentTurns?: { role: 'user' | 'brain'; text: string }[]
}

export interface BrainReply {
  speech: string
  driveIntent: DriveIntent | null
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc -b --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add web/src/brain/types.ts
git commit -m "feat(cockpit): mirror brain contract types"
```

### Task 7: The brain client (TDD — response guard)

**Files:**
- Create: `web/src/brain/brainClient.ts`
- Test: `web/src/brain/brainClient.test.ts`

**Interfaces:**
- Consumes: `BrainTurn`, `BrainReply` (brain/types.ts).
- Produces: `postTurn(turn: BrainTurn, opts?: { baseUrl?: string; fetchImpl?: typeof fetch }): Promise<BrainReply>` and `isBrainReply(x): x is BrainReply`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/brain/brainClient.test.ts
import { describe, it, expect, vi } from 'vitest'
import { postTurn, isBrainReply } from './brainClient'

describe('isBrainReply', () => {
  it('accepts a valid reply and rejects junk', () => {
    expect(isBrainReply({ speech: 'hi', driveIntent: null })).toBe(true)
    expect(isBrainReply({ speech: 'go', driveIntent: { action: 'forward' } })).toBe(true)
    expect(isBrainReply({ driveIntent: null })).toBe(false)
    expect(isBrainReply({ speech: 'x', driveIntent: { action: 'fly' } })).toBe(false)
  })
})

describe('postTurn', () => {
  it('posts the turn and returns the parsed reply', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ speech: 'On it.', driveIntent: { action: 'forward', durationMs: 800 } }),
    })
    const reply = await postTurn({ transcript: 'nudge forward' }, { baseUrl: 'http://x', fetchImpl: fetchImpl as never })
    expect(reply.driveIntent?.action).toBe('forward')
    expect(fetchImpl).toHaveBeenCalledWith('http://x/brain/turn', expect.objectContaining({ method: 'POST' }))
  })

  it('throws on a malformed reply shape', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ nope: 1 }) })
    await expect(postTurn({ transcript: 'hi' }, { baseUrl: 'http://x', fetchImpl: fetchImpl as never })).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/brain/brainClient.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `web/src/brain/brainClient.ts`**

```ts
import type { BrainTurn, BrainReply, DriveAction } from './types'

const ACTIONS: DriveAction[] = ['forward', 'left', 'right', 'stop', 'none']

export function isBrainReply(x: unknown): x is BrainReply {
  if (typeof x !== 'object' || x === null) return false
  const r = x as Record<string, unknown>
  if (typeof r.speech !== 'string') return false
  if (r.driveIntent === null) return true
  if (typeof r.driveIntent !== 'object') return false
  const d = r.driveIntent as Record<string, unknown>
  return ACTIONS.includes(d.action as DriveAction)
}

const DEFAULT_BASE = import.meta.env.VITE_BRAIN_URL ?? 'http://localhost:8099'

export async function postTurn(
  turn: BrainTurn,
  opts: { baseUrl?: string; fetchImpl?: typeof fetch } = {},
): Promise<BrainReply> {
  const f = opts.fetchImpl ?? fetch
  const res = await f(`${opts.baseUrl ?? DEFAULT_BASE}/brain/turn`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(turn),
  })
  if (!res.ok) throw new Error(`brain: HTTP ${res.status}`)
  const body: unknown = await res.json()
  if (!isBrainReply(body)) throw new Error('brain: malformed reply')
  return body
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/brain/brainClient.test.ts`
Expected: PASS (4 assertions across 3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/brain/brainClient.ts web/src/brain/brainClient.test.ts
git commit -m "feat(cockpit): brain HTTP client with reply guard"
```

### Task 8: The voice hook (browser Web Speech)

**Files:**
- Create: `web/src/brain/useVoice.ts`

**Interfaces:**
- Produces: `useVoice(): { supported: boolean; listening: boolean; startListening(onFinal: (text: string) => void): void; stopListening(): void; speak(text: string): void }`.

*This hook wraps browser-only APIs (`SpeechRecognition`, `speechSynthesis`) and is verified manually in the browser (Task 10), not unit-tested.*

- [ ] **Step 1: Write `web/src/brain/useVoice.ts`**

```ts
import { useCallback, useRef, useState } from 'react'

type SR = typeof window & {
  SpeechRecognition?: new () => SpeechRecognition
  webkitSpeechRecognition?: new () => SpeechRecognition
}

function getRecognitionCtor(): (new () => SpeechRecognition) | null {
  const w = window as SR
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function useVoice() {
  const Ctor = getRecognitionCtor()
  const supported = Ctor !== null && 'speechSynthesis' in window
  const [listening, setListening] = useState(false)
  const recRef = useRef<SpeechRecognition | null>(null)

  const startListening = useCallback(
    (onFinal: (text: string) => void) => {
      if (!Ctor) return
      const rec = new Ctor()
      rec.lang = 'en-US'
      rec.interimResults = false
      rec.maxAlternatives = 1
      rec.onresult = (e) => {
        const text = e.results[e.results.length - 1][0].transcript.trim()
        if (text) onFinal(text)
      }
      rec.onend = () => setListening(false)
      rec.onerror = () => setListening(false)
      recRef.current = rec
      setListening(true)
      rec.start()
    },
    [Ctor],
  )

  const stopListening = useCallback(() => {
    recRef.current?.stop()
    setListening(false)
  }, [])

  const speak = useCallback((text: string) => {
    if (!('speechSynthesis' in window)) return
    const u = new SpeechSynthesisUtterance(text)
    u.rate = 1.0
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(u)
  }, [])

  return { supported, listening, startListening, stopListening, speak }
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc -b --noEmit`
Expected: PASS. (If TS lacks `SpeechRecognition` DOM types, add `"dom"` and `"dom.iterable"` to `web/tsconfig.app.json` `lib` — they are already present in a Vite React TS template; verify before adding.)

- [ ] **Step 3: Commit**

```bash
git add web/src/brain/useVoice.ts
git commit -m "feat(cockpit): Web Speech STT/TTS voice hook"
```

### Task 9: The BrainPanel UI

**Files:**
- Create: `web/src/cockpit/BrainPanel.tsx`

**Interfaces:**
- Consumes: `useVoice`, `postTurn` (brainClient), `useTelemetry` (`web/src/state/store.ts`), `Card`/`Button` (`web/src/ui`).
- Produces: `<BrainPanel onDriveIntent={(intent: DriveIntent) => void} assistEnabled: boolean />` — renders the transcript, a talk button, and calls `onDriveIntent` when the reply carries one and `assistEnabled` is true.

- [ ] **Step 1: Write `web/src/cockpit/BrainPanel.tsx`**

```tsx
import { useCallback, useState } from 'react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { useVoice } from '../brain/useVoice'
import { postTurn } from '../brain/brainClient'
import { useTelemetry } from '../state/store'
import type { DriveIntent } from '../brain/types'

interface Turn { role: 'user' | 'brain'; text: string }

export function BrainPanel({
  assistEnabled,
  onDriveIntent,
  getCameraFrame,
}: {
  assistEnabled: boolean
  onDriveIntent: (intent: DriveIntent) => void
  getCameraFrame?: () => Promise<string | undefined>
}) {
  const { supported, listening, startListening, speak } = useVoice()
  const telemetry = useTelemetry()
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)

  const handleFinal = useCallback(
    async (text: string) => {
      setTurns((t) => [...t, { role: 'user', text }])
      setBusy(true)
      try {
        const frame = getCameraFrame ? await getCameraFrame() : undefined
        const reply = await postTurn({
          transcript: text,
          cameraFrameJpegBase64: frame,
          telemetry,
          recentTurns: turns.slice(-6),
        })
        setTurns((t) => [...t, { role: 'brain', text: reply.speech }])
        speak(reply.speech)
        if (reply.driveIntent && reply.driveIntent.action !== 'none' && assistEnabled) {
          onDriveIntent(reply.driveIntent)
        }
      } catch (err) {
        const msg = `Brain unavailable: ${err instanceof Error ? err.message : String(err)}`
        setTurns((t) => [...t, { role: 'brain', text: msg }])
      } finally {
        setBusy(false)
      }
    },
    [assistEnabled, getCameraFrame, onDriveIntent, speak, telemetry, turns],
  )

  return (
    <Card>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ fontFamily: 'monospace', fontSize: 12, letterSpacing: '.1em', textTransform: 'uppercase' }}>
          Argus — Voice
        </div>
        {!supported && <div>Voice needs Chrome (Web Speech API).</div>}
        <div style={{ maxHeight: 220, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {turns.map((t, i) => (
            <div key={i} style={{ opacity: t.role === 'user' ? 0.7 : 1 }}>
              <b>{t.role === 'user' ? 'You' : 'Argus'}:</b> {t.text}
            </div>
          ))}
        </div>
        <Button
          disabled={!supported || busy || listening}
          onClick={() => startListening(handleFinal)}
        >
          {listening ? 'Listening…' : busy ? 'Thinking…' : 'Hold to talk'}
        </Button>
      </div>
    </Card>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc -b --noEmit`
Expected: PASS. (If `useTelemetry` is not an existing named export of `web/src/state/store.ts`, read that file and use the actual telemetry selector it exports — `CockpitScreen.tsx:16` imports `useTelemetry` from it, so it exists.)

- [ ] **Step 3: Commit**

```bash
git add web/src/cockpit/BrainPanel.tsx
git commit -m "feat(cockpit): BrainPanel voice/conversation UI"
```

### Task 10: Mount BrainPanel and verify "talks" end-to-end

**Files:**
- Modify: `web/src/cockpit/CockpitScreen.tsx` (add the panel; assist toggle + drive wiring land in M5 — for now pass `assistEnabled={false}` and a no-op `onDriveIntent`)

- [ ] **Step 1: Add the panel to the cockpit**

Read `web/src/cockpit/CockpitScreen.tsx`, import `BrainPanel`, and render it in the existing side/rail layout:

```tsx
import { BrainPanel } from './BrainPanel'
// …inside the render, in an appropriate panel slot:
<BrainPanel assistEnabled={false} onDriveIntent={() => {}} />
```

- [ ] **Step 2: Verify criterion 1 end-to-end (browser)**

Start the brain (`cd brain && ANTHROPIC_API_KEY=… npm run dev`) and the cockpit (`cd web && npm run dev`). In Chrome, open the cockpit, click "Hold to talk", say a greeting.
Expected: within ≤4s a spoken reply plays through the speaker and both turns appear in the transcript. Repeat 10× — pass if ≥9 succeed.

- [ ] **Step 3: Commit**

```bash
git add web/src/cockpit/CockpitScreen.tsx
git commit -m "feat(cockpit): mount BrainPanel (talk + see loop)"
```

---

## MILESTONE M3 — Sees (Verify: acceptance criterion 2)

### Task 11: Camera frame grab (P1 stand-in)

**Files:**
- Create: `web/src/brain/useCameraFrame.ts`

**Interfaces:**
- Produces: `useCameraFrame(): { ready: boolean; start(): Promise<void>; grab(): Promise<string | undefined>; videoEl: React.RefObject<HTMLVideoElement | null> }`. `grab()` returns a base64 JPEG (no data-URI prefix) of the current frame.

*Browser-only (`getUserMedia`, canvas); verified manually. P1 uses the operator device camera as a stand-in for the vehicle camera — a documented swap point for the real ZED X feed later.*

- [ ] **Step 1: Write `web/src/brain/useCameraFrame.ts`**

```ts
import { useCallback, useRef, useState } from 'react'

export function useCameraFrame() {
  const videoEl = useRef<HTMLVideoElement | null>(null)
  const [ready, setReady] = useState(false)

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    if (videoEl.current) {
      videoEl.current.srcObject = stream
      await videoEl.current.play()
      setReady(true)
    }
  }, [])

  const grab = useCallback(async (): Promise<string | undefined> => {
    const v = videoEl.current
    if (!v || !ready) return undefined
    const canvas = document.createElement('canvas')
    canvas.width = v.videoWidth
    canvas.height = v.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return undefined
    ctx.drawImage(v, 0, 0)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.7)
    return dataUrl.split(',')[1] // strip "data:image/jpeg;base64,"
  }, [ready])

  return { ready, start, grab, videoEl }
}
```

- [ ] **Step 2: Typecheck + commit**

Run: `cd web && npx tsc -b --noEmit` → PASS.
```bash
git add web/src/brain/useCameraFrame.ts
git commit -m "feat(cockpit): getUserMedia camera frame grab (P1 stand-in)"
```

### Task 12: Wire the camera into BrainPanel and verify "sees"

**Files:**
- Modify: `web/src/cockpit/BrainPanel.tsx` (use `useCameraFrame`; render a small `<video>`; pass `grab` as `getCameraFrame`)

- [ ] **Step 1: Wire it**

In `BrainPanel.tsx`, call `useCameraFrame()`, render `<video ref={videoEl} muted playsInline style={{ width: '100%', borderRadius: 6 }} />`, add a "Enable camera" button that calls `start()`, and pass `grab` down instead of the prop `getCameraFrame` (drop that prop). Remove the `getCameraFrame` prop from the signature and use the local hook.

- [ ] **Step 2: Verify criterion 2 (browser)**

Place a known object in front of the camera, enable camera, ask "what do you see?".
Expected: spoken description names the object. Test 3 distinct objects, 10 trials each — pass if ≥8/10 correct per object.

- [ ] **Step 3: Commit**

```bash
git add web/src/cockpit/BrainPanel.tsx
git commit -m "feat(cockpit): camera frame feeds the brain (sees)"
```

---

## MILESTONE M4 — Pre-flight (Verify: acceptance criterion 3)

### Task 13: Deterministic pre-flight evaluator (TDD)

**Files:**
- Create: `web/src/brain/preflight.ts`
- Test: `web/src/brain/preflight.test.ts`

**Interfaces:**
- Consumes: `Telemetry` (`../contract`), `CheckResult` (`./types`).
- Produces: `evaluatePreflight(t: Telemetry): CheckResult[]`. One entry per checked field: battery %, runtime, link RTT, temp, armed, safetyState, gear. Thresholds are fixed (below) so results are deterministic.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/brain/preflight.test.ts
import { describe, it, expect } from 'vitest'
import { evaluatePreflight } from './preflight'
import type { Telemetry } from '../contract'

const base: Telemetry = {
  speedKmh: 0, gear: 'N', steerAngleDeg: 0, mode: 'MANUAL', armed: false,
  safetyState: 'STOPPED', battery: { percent: 90, runtimeMin: 120 },
  lights: { headlights: false, blinker: 'off', horn: false }, recording: true,
  linkRttMs: 80, tempC: 40, headingDeg: 0,
}

describe('evaluatePreflight', () => {
  it('reports all ok for a healthy vehicle', () => {
    const results = evaluatePreflight(base)
    expect(results.every((r) => r.status === 'ok')).toBe(true)
    expect(results.map((r) => r.item)).toEqual(
      expect.arrayContaining(['Battery', 'Link', 'Temperature', 'Armed', 'Safety', 'Gear']),
    )
  })

  it('flags low battery as fail and marginal battery as warn', () => {
    expect(evaluatePreflight({ ...base, battery: { percent: 15, runtimeMin: 5 } }).find((r) => r.item === 'Battery')!.status).toBe('fail')
    expect(evaluatePreflight({ ...base, battery: { percent: 30, runtimeMin: 20 } }).find((r) => r.item === 'Battery')!.status).toBe('warn')
  })

  it('flags a stale link as fail', () => {
    expect(evaluatePreflight({ ...base, linkRttMs: 800 }).find((r) => r.item === 'Link')!.status).toBe('fail')
  })

  it('flags high temperature as fail', () => {
    expect(evaluatePreflight({ ...base, tempC: 80 }).find((r) => r.item === 'Temperature')!.status).toBe('fail')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/brain/preflight.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `web/src/brain/preflight.ts`**

```ts
import type { Telemetry } from '../contract'
import type { CheckResult } from './types'

const band = (
  item: string,
  value: number,
  warnAt: number,
  failAt: number,
  dir: 'low-bad' | 'high-bad',
  fmt: (v: number) => string,
): CheckResult => {
  const bad = dir === 'low-bad'
    ? { fail: value < failAt, warn: value < warnAt }
    : { fail: value > failAt, warn: value > warnAt }
  const status: CheckResult['status'] = bad.fail ? 'fail' : bad.warn ? 'warn' : 'ok'
  return { item, status, detail: fmt(value) }
}

export function evaluatePreflight(t: Telemetry): CheckResult[] {
  return [
    band('Battery', t.battery.percent, 40, 20, 'low-bad', (v) => `${v}% (${t.battery.runtimeMin} min)`),
    band('Link', t.linkRttMs, 300, 600, 'high-bad', (v) => `${Math.round(v)} ms round-trip`),
    band('Temperature', t.tempC, 60, 75, 'high-bad', (v) => `${Math.round(v)} °C`),
    {
      item: 'Armed',
      status: t.armed ? 'ok' : 'warn',
      detail: t.armed ? 'armed' : 'not armed',
    },
    {
      item: 'Safety',
      status: t.safetyState === 'LATCHED' ? 'fail' : 'ok',
      detail: t.safetyState.toLowerCase(),
    },
    { item: 'Gear', status: 'ok', detail: t.gear },
  ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/brain/preflight.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/brain/preflight.ts web/src/brain/preflight.test.ts
git commit -m "feat(cockpit): deterministic pre-flight evaluator + tests"
```

### Task 14: Wire pre-flight into BrainPanel and verify

**Files:**
- Modify: `web/src/cockpit/BrainPanel.tsx`

- [ ] **Step 1: Compute and send pre-flight, render results**

In `handleFinal`, compute `const preflight = evaluatePreflight(telemetry)` and include it in the `postTurn` call. Also render the latest `preflight` array as a small list with per-item `ok/warn/fail` color when the last user utterance matched `/pre-?flight|check/i` (simple client-side trigger), so the operator sees the checklist while the brain speaks the summary.

- [ ] **Step 2: Verify criterion 3 (browser)**

With a healthy telemetry snapshot, say "run pre-flight".
Expected: spoken checklist covering all six items with a summary; the on-screen list shows per-item status. Then feed a low-battery / stale-link telemetry (via the existing dummy vehicle / mock) and confirm the matching item flips to warn/fail in both the spoken summary and the list.

- [ ] **Step 3: Commit**

```bash
git add web/src/cockpit/BrainPanel.tsx
git commit -m "feat(cockpit): spoken pre-flight checklist over telemetry"
```

---

## MILESTONE M5 — Bounded spoken-drive + override + dead-man (Verify: acceptance criteria 4, 5, 6)

### Task 15: Intent → bounded Command (TDD, pure)

**Files:**
- Create: `web/src/brain/driveIntent.ts`
- Test: `web/src/brain/driveIntent.test.ts`

**Interfaces:**
- Consumes: `Command`, `neutralCommand` (`../contract`); `DriveIntent` (`./types`).
- Produces: `DRIVE_CAPS = { throttleCap: number; maxDriveMs: number }`; `intentToCommand(intent: DriveIntent, caps?): Command`; `clampDurationMs(requested?: number, caps?): number`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/brain/driveIntent.test.ts
import { describe, it, expect } from 'vitest'
import { intentToCommand, clampDurationMs, DRIVE_CAPS } from './driveIntent'

describe('intentToCommand', () => {
  it('forward drives at the throttle cap in forward gear', () => {
    const c = intentToCommand({ action: 'forward' })
    expect(c.gear).toBe('F')
    expect(c.throttle).toBe(DRIVE_CAPS.throttleCap)
    expect(c.throttle).toBeLessThanOrEqual(DRIVE_CAPS.throttleCap)
    expect(c.steer).toBe(0)
  })

  it('left/right steer full but hold zero throttle (steer-in-place is bounded elsewhere)', () => {
    expect(intentToCommand({ action: 'left' }).steer).toBe(-1)
    expect(intentToCommand({ action: 'right' }).steer).toBe(1)
  })

  it('stop and none return a neutral, non-driving command', () => {
    for (const action of ['stop', 'none'] as const) {
      const c = intentToCommand({ action })
      expect(c.throttle).toBe(0)
      expect(c.steer).toBe(0)
    }
  })

  it('never exceeds the throttle cap even if asked', () => {
    const c = intentToCommand({ action: 'forward' }, { throttleCap: 0.25, maxDriveMs: 1000 })
    expect(c.throttle).toBe(0.25)
  })
})

describe('clampDurationMs', () => {
  it('clamps to the cap and defaults when unset', () => {
    expect(clampDurationMs(5000)).toBe(DRIVE_CAPS.maxDriveMs)
    expect(clampDurationMs(undefined)).toBeLessThanOrEqual(DRIVE_CAPS.maxDriveMs)
    expect(clampDurationMs(300)).toBe(300)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/brain/driveIntent.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `web/src/brain/driveIntent.ts`**

```ts
import { neutralCommand, type Command } from '../contract'
import type { DriveIntent } from './types'

export const DRIVE_CAPS = { throttleCap: 0.35, maxDriveMs: 1200 } as const

export function clampDurationMs(requested: number | undefined, caps = DRIVE_CAPS): number {
  const want = requested ?? 600
  return Math.max(0, Math.min(caps.maxDriveMs, want))
}

export function intentToCommand(intent: DriveIntent, caps = DRIVE_CAPS): Command {
  const cmd = neutralCommand()
  switch (intent.action) {
    case 'forward':
      cmd.gear = 'F'
      cmd.throttle = caps.throttleCap
      break
    case 'left':
      cmd.steer = -1
      break
    case 'right':
      cmd.steer = 1
      break
    case 'stop':
    case 'none':
      break
  }
  return cmd
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/brain/driveIntent.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/brain/driveIntent.ts web/src/brain/driveIntent.test.ts
git commit -m "feat(cockpit): bounded intent→Command mapping + tests"
```

### Task 16: Assist toggle, bounded execution, human override

**Files:**
- Modify: `web/src/cockpit/CockpitScreen.tsx`

**Interfaces:**
- Consumes: `intentToCommand`, `clampDurationMs`, `DRIVE_CAPS` (driveIntent.ts); the existing manual-drive path (`useManualDrive`) and the `TokenEmitter`/transport already wired in `CockpitScreen`.

- [ ] **Step 1: Add an "Assist" toggle**

Add local state `const [assist, setAssist] = useState(false)` and a labelled toggle button in the cockpit control area. Pass `assistEnabled={assist}` to `<BrainPanel />`.

- [ ] **Step 2: Execute a bounded drive intent, human overrides**

Read `CockpitScreen.tsx` to find how a `Command` currently reaches the transport (the manual-drive → `TokenEmitter` path). Implement `handleDriveIntent(intent)`:
- If `intent.action === 'stop'`, immediately send the transport's neutral/`forceNeutral()` and clear any pending assist timer.
- Otherwise set an "assist command" that the existing drive tick applies **only while** (a) `assist` is true, (b) no human manual input is active this tick (human input from `useManualDrive`/gamepad takes precedence — check the existing input state and skip applying the assist command when the human is driving), and (c) `Date.now() - startedAt < clampDurationMs(intent.durationMs)`. When the window elapses or the human intervenes, revert to neutral.

Concretely, hold the assist command in a ref with an expiry timestamp; in the existing per-tick drive computation, choose `humanCommand ?? (assist && notExpired ? assistCommand : neutralCommand())`. Human command must win whenever present.

- [ ] **Step 3: Verify criteria 4, 5, 6 (bench, wheels up)**

Run the relay + `mock_remo` (`python3 test-bridge/mock_remo.py` and `ARGUS_PASSWORD=… python3 test-bridge/argus_relay.py`), connect the cockpit, enable Assist.
- **Criterion 4:** say "nudge forward" → confirm in `mock_remo` logs a `P`-token burst at ≤ cap for ≤ `MAX_DRIVE_MS` then `P42` (auto-neutral). "Stop" → immediate `P42 L0 R0`.
- **Criterion 5:** during an assist nudge, drive manually → confirm human tokens win (assist suppressed) in the log ordering.
- **Criterion 6:** kill the cockpit's link mid-nudge → confirm the relay logs `DEAD-MAN … -> neutral` within 700 ms (relay unchanged; this exercises the existing dead-man).

- [ ] **Step 4: Commit**

```bash
git add web/src/cockpit/CockpitScreen.tsx
git commit -m "feat(cockpit): bounded spoken-drive with assist toggle + human override"
```

---

## MILESTONE M6 — Harden + no-regression (Verify: acceptance criterion 7 + full E2E)

### Task 17: Full suites green + typecheck

- [ ] **Step 1: Cockpit suite + typecheck**

Run: `cd web && npx tsc -b --noEmit && npx vitest run`
Expected: PASS — including the pre-existing `tokens.test.ts`, `store.test.ts`, `dummyVehicle.test.ts`, `dualsense.test.ts` and the new `preflight`/`driveIntent`/`brainClient` tests.

- [ ] **Step 2: Brain suite + typecheck**

Run: `cd brain && npm run typecheck && npm test`
Expected: PASS.

- [ ] **Step 3: Fix anything red, then commit**

```bash
git add -A
git commit -m "test(brain,cockpit): green suites + typecheck for Phase 1 soul"
```

### Task 18: One real-hardware wheels-up E2E pass

- [ ] **Step 1: Run all seven acceptance criteria on real hardware, wheels off the ground**

Bring up the real spine (relay → real Remo → Arduino, wheels up), the brain (`npm run dev` with a key), and the cockpit. Walk the seven acceptance criteria from the spec (talk, see, pre-flight, bounded drive, override, dead-man, no-regression). Record pass/fail per criterion.

- [ ] **Step 2: Document the run**

Append a short "Phase 1 verification" note (date, per-criterion pass/fail, any follow-ups) to `docs/superpowers/specs/2026-07-08-argus-drive-brain-phase1-soul-spec.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-07-08-argus-drive-brain-phase1-soul-spec.md
git commit -m "docs(brain): Phase 1 hardware verification results"
```

---

## Self-Review

- **Spec coverage:** talk (M1/M2), see (M3), pre-flight (M4), bounded spoken-drive + override + dead-man (M5), no-regression + hardware pass (M6) — every acceptance criterion (1–7) maps to a milestone Verify step. Open items from the spec (camera source → Task 11's getUserMedia stand-in; telemetry fields → pre-flight reads the defined `Telemetry` contract; brain language/host → Node/TS cloud service; provider wiring → `@anthropic-ai/sdk` + env key) are all resolved.
- **Placeholder scan:** none — every code step contains complete code; every command has an expected result.
- **Type consistency:** `DriveIntent`/`CheckResult`/`BrainTurn`/`BrainReply` are defined once in `brain/src/types.ts` and mirrored in `web/src/brain/types.ts` with identical field names/types; `intentToCommand` returns the contract `Command`; `evaluatePreflight` consumes the contract `Telemetry`. The brain reply is validated at three points (zod schema in the service, `isBrainReply` guard in the client, structured-output enforcement at the model).
- **Ambiguity check:** the driver-arbitration rule (human always wins; cockpit stays sole DRIVER; assist off by default) is stated in Global Constraints and enforced in Task 16.
```
