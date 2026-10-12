import { useEffect, useMemo, useRef, useState } from 'react'
import { useVehicleStore } from '../state/store'
import { BridgeTransport } from './bridgeTransport'
import type { LinkStatus } from './remoTransport'
import type { DriveRole, RemoLink } from './useRemoTransport'
import type { Command, SessionFacts } from '../contract'
import { driveActiveNow, subscribeDriveActive, subscribeSignOut } from '../embed/driveActive'

/**
 * Live link to the ARGUS DRIVE bridge daemon. Activated by a URL param so the
 * mock app is untouched:  ?bridge=<host>[:port]   e.g.  ?bridge=ugv-01:8090
 *
 * Unlike the Remo token link, the bridge owns safety on the vehicle side and
 * streams real telemetry back; while this link is live the store's telemetry
 * is the vehicle's, not the local sim's.
 */
interface BridgeTarget {
  url: string
  label: string
}

function parseBridgeParam(): BridgeTarget | null {
  if (typeof window === 'undefined') return null
  const raw = new URLSearchParams(window.location.search).get('bridge')
  if (!raw) return null
  if (/^wss?:\/\//.test(raw)) return { url: raw.replace(/\/$/, ''), label: raw }
  const https = window.location.protocol === 'https:'
  const hostport = raw.includes(':') ? raw : https ? raw : `${raw}:8090`
  const scheme = https ? 'wss' : 'ws'
  return { url: `${scheme}://${hostport}`, label: hostport }
}

/**
 * How long the link may go without vehicle telemetry before it counts as
 * stale, when the vehicle has not declared its own watchdog window.
 */
export const DEFAULT_STALE_MS = 1000

export interface BridgeOptions {
  /** Command frames per second while Drive is active. */
  hz?: number
}

export interface BridgeLink extends RemoLink {
  /** The last session facts the vehicle gave, kept after the link drops. */
  lastSession: SessionFacts | null
}

/**
 * The arm bit on the wire is the operator's arm, and only while this
 * cockpit holds control: Drive active, the operator past the connect step,
 * the link open with fresh telemetry, and no relinquish since the operator
 * last pressed arm. Telemetry never asserts it.
 */
export function outgoing(cmd: Command, mayArm: boolean): Command {
  return { ...cmd, safety: { arm: mayArm && cmd.safety.arm, estop: cmd.safety.estop } }
}

/**
 * Whether Drive is the active screen is read from the embed module at the
 * moment of each frame, and a change is acted on in the same turn as C2's
 * message. Leaving Drive relinquishes control: the arm drops, steer and
 * throttle go to zero, that frame is sent at once, and command frames
 * stop. Heartbeats continue so the link stays measured and the seat is
 * kept. Coming back resumes the loop with the arm down. This is not the
 * latched stop.
 *
 * The link is live only while vehicle telemetry is fresh. No telemetry
 * for longer than the vehicle's declared watchdog window is treated as
 * link loss, even when the socket says it is open.
 */
export function useBridgeTransport(
  password: string | null,
  live: boolean,
  { hz = 15 }: BridgeOptions = {},
): BridgeLink {
  const target = useMemo(() => parseBridgeParam(), [])
  const [status, setStatus] = useState<LinkStatus>('connecting')
  const [role, setRole] = useState<DriveRole>(null)
  const [authFailed, setAuthFailed] = useState(false)
  const [session, setSession] = useState<SessionFacts | null>(null)
  const [lastSession, setLastSession] = useState<SessionFacts | null>(null)
  const [everOpen, setEverOpen] = useState(false)

  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  }, [live])

  useEffect(() => {
    if (!target || !password) return
    const store = useVehicleStore
    const t = new BridgeTransport(target.url, password)
    store.getState().setLinked(true)

    // True from the moment control is given up (Drive left, the link lost
    // or stale) until the operator arms again while active on a live
    // link. While true this cockpit never asserts arm, whatever the store
    // or the telemetry says.
    let relinquished = true
    let linkOpen = false
    // Vehicle telemetry has arrived within the watchdog window.
    let fresh = false
    let lastHeard = 0
    let staleMs = DEFAULT_STALE_MS
    let signedOut = false
    const mayArm = () => liveRef.current && driveActiveNow() && linkOpen && fresh && !relinquished
    const loseLink = () => {
      relinquished = true
      fresh = false
      store.getState().loseLink()
      store.getState().setRemote(false)
    }

    t.onStatus = (s) => {
      setStatus(s)
      const wasOpen = linkOpen
      linkOpen = s === 'open' && !signedOut
      if (linkOpen) {
        // Open is not live: the vehicle has to speak first.
        lastHeard = Date.now()
        fresh = false
        store.getState().setRemote(false)
      } else {
        setRole(null)
        setSession(null)
        // Link loss is a relinquish: the new session waits for a fresh arm.
        if (wasOpen) loseLink()
        relinquished = true
        fresh = false
        store.getState().setRemote(false)
      }
      if (s === 'connecting') setAuthFailed(false)
    }
    t.onRole = (r) => setRole(r === 'DRIVER' || r === 'SPECTATOR' ? r : null)
    t.onSession = (facts) => {
      staleMs = facts.watchdogMs ?? DEFAULT_STALE_MS
      setSession(facts)
      setLastSession(facts)
    }
    t.onAuthFail = () => setAuthFailed(true)
    t.onTelemetry = (tel) => {
      if (!linkOpen) return
      lastHeard = Date.now()
      if (!fresh) {
        fresh = true
        setEverOpen(true)
        store.getState().setRemote(true)
      }
      store.getState().applyRemoteTelemetry(tel)
    }
    t.onPreflight = (p) => store.getState().applyPreflight(p)

    // Revocation is synchronous: C2's message, then this, then nothing.
    let wasActive = driveActiveNow()
    const unsubActive = subscribeDriveActive(() => {
      const nowActive = driveActiveNow()
      if (nowActive === wasActive) return
      wasActive = nowActive
      if (nowActive) return // the arm stays down until the operator arms
      relinquished = true
      store.getState().relinquish()
      // A cmd frame without arm disarms the daemon's watchdog to STOPPED
      // (no latch). It goes now, not on the next interval.
      if (linkOpen) t.send(outgoing(store.getState().command, false))
    })

    // Sign-out: disarm explicitly, then close cleanly so the daemon logs
    // a session close, not a latch on link loss. The auth module forgets
    // the key on the same message.
    const unsubSignOut = subscribeSignOut(() => {
      if (signedOut) return
      relinquished = true
      store.getState().relinquish()
      if (linkOpen) t.send(outgoing(store.getState().command, false))
      signedOut = true
      linkOpen = false
      fresh = false
      store.getState().setRemote(false)
      t.close()
    })

    t.connect()

    const framesPerBeat = Math.max(1, Math.round(hz / 5))
    let n = 0
    const id = setInterval(() => {
      if (signedOut) return
      if (linkOpen && Date.now() - lastHeard > staleMs) {
        // A stalled socket that never closed: treat it as link loss.
        const hadControl = fresh || !relinquished
        loseLink()
        if (hadControl && driveActiveNow()) t.send(outgoing(store.getState().command, false))
        lastHeard = Date.now()
      }
      store.getState().settleArm()
      if (driveActiveNow()) t.send(outgoing(store.getState().command, mayArm()))
      if (++n % framesPerBeat === 0) t.heartbeat()
    }, 1000 / hz)

    // momentary edges must not fall between interval samples
    const unsub = store.subscribe((state, prev) => {
      if (state.command.safety.estop && !prev.command.safety.estop) t.estop()
      else if (state.armPresses !== prev.armPresses && driveActiveNow() && liveRef.current && linkOpen && fresh) {
        relinquished = false // the operator's fresh arm
        t.send(outgoing(state.command, mayArm()))
      }
    })

    const onHide = () => t.close()
    window.addEventListener('pagehide', onHide)
    window.addEventListener('beforeunload', onHide)

    return () => {
      clearInterval(id)
      unsub()
      unsubActive()
      unsubSignOut()
      window.removeEventListener('pagehide', onHide)
      window.removeEventListener('beforeunload', onHide)
      store.getState().setRemote(false)
      store.getState().setLinked(false)
      t.close()
    }
  }, [target, password, hz])

  return {
    active: !!target,
    label: target?.label ?? '',
    status,
    role,
    authFailed,
    session,
    lastSession,
    everOpen,
    hz,
  }
}
