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
