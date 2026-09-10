/**
 * The shell, tested where being wrong strands an operator.
 *
 * A stored token that the site no longer accepts used to leave the station
 * reading "site link lost" for ever, with no way back to sign-in: the site
 * was fine, we were refused. Both refusal paths (REST 401, stream close
 * 4401) must end at the sign-in screen. And the dock must be out of the way
 * while an application is open: at 1280 wide it covered Drive's controls.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./Operate', () => ({ Operate: () => <div>operate-screen</div> }))

import { App } from './App'
import { CLOSE_NOT_SIGNED_IN } from '../sdk/stream'
import { say } from './wording'

/** A stand-in for the browser's WebSocket that the test can drive. */
class FakeSocket {
  static last: FakeSocket | undefined
  onopen: (() => void) | null = null
  onmessage: ((m: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  constructor(public url: string) {
    FakeSocket.last = this
  }
  close() {
    /* closed by the application; nothing to report */
  }
  open() {
    this.onopen?.()
    this.onmessage?.({
      data: JSON.stringify({
        kind: 'snapshot',
        data: { assets: [], telemetry: [], tracks: [], zones: [], tasks: [], events: [] },
      }),
    })
  }
}

/**
 * Node's own experimental `localStorage` global shadows jsdom's under this
 * runner, so the tests bring a plain in-memory one.
 */
function memoryStorage(): Storage {
  const m = new Map<string, string>()
  return {
    get length() { return m.size },
    clear: () => m.clear(),
    getItem: (k: string) => m.get(k) ?? null,
    key: (i: number) => [...m.keys()][i] ?? null,
    removeItem: (k: string) => { m.delete(k) },
    setItem: (k: string, v: string) => { m.set(k, String(v)) },
  }
}

function okJson(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}
function refused(status: number) {
  return { ok: false, status, json: async () => ({ detail: 'not signed in' }) } as Response
}

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage())
  window.localStorage.setItem('argus.token', 'stale')
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => window.setTimeout(() => cb(0), 0))
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('a token the site refuses', () => {
  it('returns to sign-in when a request is answered 401', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => refused(401)))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('heading', { name: say.signIn.title })).toBeTruthy())
    expect(window.localStorage.getItem('argus.token')).toBeNull()
  })

  it('returns to sign-in when the stream is closed as not signed in', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.onclose?.({ code: CLOSE_NOT_SIGNED_IN })
    await waitFor(() => expect(screen.getByRole('heading', { name: say.signIn.title })).toBeTruthy())
    // and it did not try again with the same token
    expect(window.localStorage.getItem('argus.token')).toBeNull()
  })

  it('does not call an ordinary drop a refusal', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.onclose?.({ code: 1006 })
    await waitFor(() => expect(screen.getByText(say.link.lost)).toBeTruthy())
    expect(screen.queryByRole('heading', { name: say.signIn.title })).toBeNull()
  })
})

describe('a refusal that arrives late', () => {
  // The operator signed in again with a new key while an old request or
  // an old stream was still out. Its refusal is about the old key and
  // must not end the new session.
  it('about an old token does not sign out a fresh session', async () => {
    let answer401: (() => void) | undefined
    const slow = new Promise<Response>((resolve) => {
      answer401 = () => resolve(refused(401))
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        // The very first /v1/me call hangs; everything after answers well.
        typeof url === 'string' && url.endsWith('/v1/me') && answer401 && !(slow as unknown as { done?: boolean }).done
          ? ((slow as unknown as { done?: boolean }).done = true, slow)
          : okJson({ display_name: 'Akash', roles: ['operator'] }),
      ),
    )
    render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    // A fresh sign-in with a different key, as if the operator typed it.
    window.localStorage.setItem('argus.token', 'fresh')
    answer401!()
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(screen.queryByRole('heading', { name: say.signIn.title })).toBeNull()
    expect(window.localStorage.getItem('argus.token')).toBe('fresh')
  })

  it('on an old stream does not sign out a fresh session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    const old = FakeSocket.last!
    window.localStorage.setItem('argus.token', 'fresh')
    old.onclose?.({ code: CLOSE_NOT_SIGNED_IN })
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(screen.queryByRole('heading', { name: say.signIn.title })).toBeNull()
    expect(window.localStorage.getItem('argus.token')).toBe('fresh')
  })
})

describe('the dock', () => {
  it('is put away while an application is open, and has no hover strip', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const { container } = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    const dock = container.querySelector('.dock')!
    expect(dock.classList.contains('is-away')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: say.shell.apps.operate }))
    await waitFor(() => expect(dock.classList.contains('is-away')).toBe(true))
    expect(dock.getAttribute('aria-hidden')).toBe('true')
    expect(container.querySelector('.dock-reveal')).toBeNull()
  })
})
