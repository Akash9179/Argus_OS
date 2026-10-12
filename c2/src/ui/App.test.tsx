/**
 * The shell, tested where being wrong strands an operator.
 *
 * A stored token that the site no longer accepts used to leave the station
 * reading "site link lost" for ever, with no way back to sign-in: the site
 * was fine, we were refused. Both refusal paths (REST 401, stream close
 * 4401) must end at the sign-in screen. And the dock must be out of the way
 * while an application is open: at 1280 wide it covered Drive's controls.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./Operate', () => ({ Operate: () => <div>operate-screen</div> }))

import { App } from './App'
import { CLOSE_NOT_SIGNED_IN } from '../sdk/stream'
import { say } from './wording'
import { DRIVE_SIGNOUT_WAIT_MS, driveOrigin, driveUrl } from './driveUrl'

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

describe('leaving Drive', () => {
  // Founder decision, 12 Oct 2026: leaving Drive relinquishes control. The
  // cockpit frame stays mounted, so C2 must tell it which screen is up.
  it('tells the cockpit frame whether Drive is the active screen', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const { container } = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    const tab = (name: string) =>
      screen.getAllByRole('button', { name }).find((b) => b.classList.contains('tab'))!

    fireEvent.click(tab(say.shell.apps.drive))
    const frame = container.querySelector('iframe.drive-frame') as HTMLIFrameElement
    expect(frame).toBeTruthy()
    const post = vi.spyOn(frame.contentWindow!, 'postMessage').mockImplementation(() => {})
    const origin = new URL(driveUrl()).origin
    expect(origin).not.toBe('*')

    fireEvent.click(tab(say.shell.apps.operate))
    await waitFor(() =>
      expect(post).toHaveBeenLastCalledWith({ type: 'argus.drive.active', active: false }, origin),
    )

    fireEvent.click(tab(say.shell.apps.drive))
    await waitFor(() =>
      expect(post).toHaveBeenLastCalledWith({ type: 'argus.drive.active', active: true }, origin),
    )

    // and once when the frame loads, so a reload hears where it stands
    post.mockClear()
    fireEvent.load(frame)
    expect(post).toHaveBeenCalledWith({ type: 'argus.drive.active', active: true }, origin)
  })
})

describe('signing out', () => {
  // The bug this pins: the button handed its click event to signOut as if
  // it were a refused token, so the sign-out was ignored as a late refusal.
  it('returns to sign-in and takes the Drive frame down with it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const { container } = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    const driveTab = screen.getAllByRole('button', { name: say.shell.apps.drive }).find((b) => b.classList.contains('tab'))!
    fireEvent.click(driveTab)
    expect(container.querySelector('iframe.drive-frame')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: say.signOut }))
    await waitFor(() => expect(screen.getByRole('heading', { name: say.signIn.title })).toBeTruthy())
    expect(window.localStorage.getItem('argus.token')).toBeNull()
    expect(container.querySelector('iframe.drive-frame')).toBeNull()
  })
})

describe('signing out with Drive open', () => {
  // The cockpit keeps the bridge key in its tab's storage. Sign-out used to
  // leave the next operator holding it, and signing out while armed was
  // logged as link loss rather than an explicit disarm. So the frame is
  // told, first that Drive is no longer active and then that the session
  // ended, at its own origin, while it is still there to hear it.
  async function signOutFromDrive(how: 'button' | 'refusal') {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const { container } = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    const driveTab = screen.getAllByRole('button', { name: say.shell.apps.drive }).find((b) => b.classList.contains('tab'))!
    fireEvent.click(driveTab)
    const frame = container.querySelector('iframe.drive-frame') as HTMLIFrameElement
    const heard: { message: unknown; origin: string; frameThere: boolean }[] = []
    vi.spyOn(frame.contentWindow!, 'postMessage').mockImplementation(((message: unknown, origin: string) => {
      heard.push({ message, origin, frameThere: frame.isConnected })
    }) as typeof window.postMessage)

    if (how === 'button') fireEvent.click(screen.getByRole('button', { name: say.signOut }))
    else FakeSocket.last!.onclose?.({ code: CLOSE_NOT_SIGNED_IN })
    await waitFor(() => expect(screen.getByRole('heading', { name: say.signIn.title })).toBeTruthy())
    expect(container.querySelector('iframe.drive-frame')).toBeNull()
    return heard
  }

  it('posts active=false, then signout, to the cockpit origin before the frame is gone', async () => {
    const heard = await signOutFromDrive('button')
    const origin = driveOrigin()
    expect(origin).not.toBe('*')
    expect(heard.slice(-2)).toEqual([
      { message: { type: 'argus.drive.active', active: false }, origin, frameThere: true },
      { message: { type: 'argus.drive.signout' }, origin, frameThere: true },
    ])
  })

  it('does the same when the site refuses the token', async () => {
    const heard = await signOutFromDrive('refusal')
    expect(heard.slice(-1)[0]).toEqual({ message: { type: 'argus.drive.signout' }, origin: driveOrigin(), frameThere: true })
  })
})

describe('the Drive frame on sign-out', () => {
  // Codex P2. postMessage is delivered later, so a frame taken down in the
  // same turn may never hear the sign-out: no explicit disarm, and the
  // bridge key left in the cockpit's storage. C2 keeps the frame until the
  // cockpit says its cleanup is done, or for DRIVE_SIGNOUT_WAIT_MS.
  async function driveOpenThenSignOut() {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const view = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    const driveTab = screen.getAllByRole('button', { name: say.shell.apps.drive }).find((b) => b.classList.contains('tab'))!
    fireEvent.click(driveTab)
    const frame = view.container.querySelector('iframe.drive-frame') as HTMLIFrameElement
    vi.spyOn(frame.contentWindow!, 'postMessage').mockImplementation(() => {})
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: say.signOut }))
    return { frame, container: view.container }
  }
  const frameThere = (container: HTMLElement) => container.querySelector('iframe.drive-frame') !== null
  const signInShown = () => screen.queryByRole('heading', { name: say.signIn.title }) !== null
  function ack(source: Window, origin: string) {
    act(() => {
      window.dispatchEvent(new MessageEvent('message', { data: { type: 'argus.drive.signout.done' }, origin, source }))
    })
  }
  afterEach(() => {
    vi.useRealTimers()
  })

  it('stays mounted until the cockpit says its cleanup is done', async () => {
    const { frame, container } = await driveOpenThenSignOut()
    act(() => vi.advanceTimersByTime(DRIVE_SIGNOUT_WAIT_MS - 100))
    expect(frameThere(container)).toBe(true)
    expect(signInShown()).toBe(false)

    ack(frame.contentWindow!, driveOrigin())
    expect(frameThere(container)).toBe(false)
    expect(signInShown()).toBe(true)
  })

  it('goes after the wait when no answer comes', async () => {
    const { container } = await driveOpenThenSignOut()
    act(() => vi.advanceTimersByTime(DRIVE_SIGNOUT_WAIT_MS - 1))
    expect(frameThere(container)).toBe(true)
    act(() => vi.advanceTimersByTime(1))
    expect(frameThere(container)).toBe(false)
    expect(signInShown()).toBe(true)
  })

  it('does not take an answer from another origin or another window', async () => {
    const { frame, container } = await driveOpenThenSignOut()
    ack(frame.contentWindow!, 'http://elsewhere.example')
    ack(window, driveOrigin())
    expect(frameThere(container)).toBe(true)
    act(() => vi.advanceTimersByTime(DRIVE_SIGNOUT_WAIT_MS))
    expect(frameThere(container)).toBe(false)
  })

  it('does not wait when Drive was never opened', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: say.signOut }))
    expect(signInShown()).toBe(true)
  })
})

describe('Esc inside the Drive frame', () => {
  // The cockpit has its own window, so C2 never hears an Esc pressed in
  // it. The cockpit posts argus.drive.escape to its parent instead, and C2
  // believes it only from that frame and that origin.
  async function openDrive() {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const view = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    const driveTab = screen.getAllByRole('button', { name: say.shell.apps.drive }).find((b) => b.classList.contains('tab'))!
    fireEvent.click(driveTab)
    const frame = view.container.querySelector('iframe.drive-frame') as HTMLIFrameElement
    const desktop = view.container.querySelector('.desktop')!
    expect(desktop.classList.contains('is-away')).toBe(true)
    return { frame, desktop }
  }
  function escapeFrom(source: Window, origin: string) {
    window.dispatchEvent(new MessageEvent('message', { data: { type: 'argus.drive.escape' }, origin, source }))
  }

  it('returns to the desktop when the cockpit frame says so', async () => {
    const { frame, desktop } = await openDrive()
    const post = vi.spyOn(frame.contentWindow!, 'postMessage').mockImplementation(() => {})
    escapeFrom(frame.contentWindow!, driveOrigin())
    await waitFor(() => expect(desktop.classList.contains('is-away')).toBe(false))
    expect(post).toHaveBeenLastCalledWith({ type: 'argus.drive.active', active: false }, driveOrigin())
  })

  it('ignores the same message from another origin', async () => {
    const { frame, desktop } = await openDrive()
    escapeFrom(frame.contentWindow!, 'http://elsewhere.example')
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(desktop.classList.contains('is-away')).toBe(true)
  })

  it('ignores the same message from another window', async () => {
    const { desktop } = await openDrive()
    escapeFrom(window, driveOrigin())
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(desktop.classList.contains('is-away')).toBe(true)
  })
})

describe('the settings window', () => {
  it('names its close button in words from wording.ts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const { container } = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    const close = container.querySelector('.swin-close')!
    expect(close.getAttribute('aria-label')).toBe(say.shell.settings.close)
    expect(close.getAttribute('title')).toBe(say.shell.settings.closeHint)
  })
})

describe('the launcher', () => {
  // Founder decision, 12 Oct 2026: phantom applications go. The top bar
  // and the dock offer only what exists.
  async function station() {
    vi.stubGlobal('fetch', vi.fn(async () => okJson({ display_name: 'Akash', roles: ['operator'] })))
    const view = render(<App />)
    await waitFor(() => expect(FakeSocket.last).toBeTruthy())
    FakeSocket.last!.open()
    return view
  }

  it('offers Operate and Drive in the top bar and Operate, Drive and Settings in the dock', async () => {
    const { container } = await station()
    const tabs = [...container.querySelectorAll('.topbar .tabs > *')].map((t) => t.textContent)
    expect(tabs).toEqual([say.shell.apps.operate, say.shell.apps.drive])
    const dock = [...container.querySelectorAll('.dock .dock-name')].map((n) => n.textContent)
    expect(dock).toEqual([say.shell.apps.operate, say.shell.apps.drive, say.shell.settings.title])
    expect(container.querySelector('.tab.soon, .dock-app.is-disabled')).toBeNull()
    for (const gone of ['Review', 'Intel', 'Fleet']) expect(screen.queryByText(gone)).toBeNull()
  })

  it('shows only the settings that exist: Appearance and Time', async () => {
    const { container } = await station()
    const nav = [...container.querySelectorAll('.swin-side .snav')].map((n) => n.textContent)
    expect(nav).toEqual([say.shell.settings.nav.appearance, say.shell.settings.nav.time])
    expect(container.querySelector('.snav.is-inert')).toBeNull()
  })
})
