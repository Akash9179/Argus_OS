/**
 * The only way this application reaches the world model.
 *
 * C2 is application number one on what later becomes the published SDK, so
 * it uses exactly the public service interfaces and nothing else: no direct
 * database access, no private endpoints, no back doors. If a screen needs
 * something these interfaces cannot express, the interface is what changes.
 * That is the SDK honesty law, and this file is where it is kept.
 */

import type {
  Asset,
  Principal,
  SystemsView,
  Task,
  TaskPreview,
  TaskRequest,
  TileLayerInfo,
  Track,
  WorldEvent,
  Zone,
} from './types'

import { savedToken, signOut } from './session'

export { forgetToken, saveToken, savedToken } from './session'

export class NotSignedIn extends Error {}
export class Refused extends Error {}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = savedToken()
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  })

  if (response.status === 401) {
    // The token we hold is no longer accepted. Drop it and let the shell
    // return to sign-in; the caller still gets the refusal it asked for.
    // This assumes the server answers 401 only for a bad token, which
    // track/api.py does; a proxy that invented 401s would end sessions.
    const text = await refusalText(response)
    signOut(token)
    throw new NotSignedIn(text)
  }
  if (!response.ok) throw new Refused(await refusalText(response))
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/**
 * The server words its own refusals, from its language file. Showing our
 * own sentence here would put a second voice in the product.
 */
async function refusalText(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    /* a refusal without a body is still a refusal */
  }
  return ''
}

export const track = {
  /** Who is signed in, as a name. The identifier stays on the server. */
  me: () => call<Principal>('/v1/me'),
  assets: () => call<Asset[]>('/v1/assets'),
  tracks: () => call<Track[]>('/v1/tracks'),
  zones: () => call<Zone[]>('/v1/zones'),
  tasks: (assetId?: string) =>
    call<Task[]>('/v1/tasks' + (assetId ? `?asset_id=${encodeURIComponent(assetId)}` : '')),
  events: (limit = 100) => call<WorldEvent[]>(`/v1/events?limit=${limit}`),

  /** Set how much the platform may do with a machine unasked. */
  setAutonomy: (assetId: string, mode: string) =>
    call<Asset>(`/v1/assets/${encodeURIComponent(assetId)}/autonomy`, {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    }),

  issueTask: (body: TaskRequest) =>
    call<Task>('/v1/tasks', { method: 'POST', body: JSON.stringify(body) }),

  /**
   * What would happen if this order were sent: the path, the checks the
   * world model ran, and whether it can go. Nothing is issued by asking.
   * The checks are the server's, so every application sees the same ones.
   */
  previewTask: (body: TaskRequest) =>
    call<TaskPreview>('/v1/tasks/preview', { method: 'POST', body: JSON.stringify(body) }),

  /** What a machine has reported about its own systems, in operator words. */
  systems: (assetId: string) =>
    call<SystemsView>(`/v1/assets/${encodeURIComponent(assetId)}/systems`),

  /** Imagery held in this station's local cache. Empty until tiles are sourced. */
  tiles: () => call<{ layers: TileLayerInfo[] }>('/v1/tiles'),

  /**
   * The frozen contract has no cancel message, so a cancellation travels as
   * a task carrying the cancelled state. The server owns that convention;
   * this endpoint is the only thing C2 knows about it.
   */
  cancelTask: (taskId: string) =>
    call<Task>(`/v1/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' }),

  /** Used once at sign-in to check a token before we keep it. */
  checkToken: async (token: string): Promise<boolean> => {
    const response = await fetch('/v1/assets', { headers: { Authorization: `Bearer ${token}` } })
    return response.ok
  },
}
