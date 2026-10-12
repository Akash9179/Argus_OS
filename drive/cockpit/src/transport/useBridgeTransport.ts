import { useEffect, useMemo, useRef, useState } from 'react'
import { useVehicleStore } from '../state/store'
import { BridgeTransport } from './bridgeTransport'
import type { LinkStatus } from './remoTransport'
import type { DriveRole, RemoLink } from './useRemoTransport'
import type { Command, SessionFacts } from '../contract'

/**
 * Live link to the ARGUS DRIVE bridge daemon. Activated by a URL param so the
 * mock app is untouched:  ?bridge=<host>[:port]   e.g.  ?bridge=ugv-01:8090
 *
 * Unlike the Remo token link, the bridge owns safety on the vehicle side and
 * streams real telemetry back; while this link is open the store's telemetry
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

export interface BridgeOptions {
  /** Command frames per second while Drive is active. */
  hz?: number
  /**
   * Whether Drive is the operator's active screen. Leaving it relinquishes
   * control: the arm drops, steer and throttle go to zero, that frame is
   * sent at once, and command frames stop. Heartbeats continue so the link
   * stays measured and the seat is kept. Coming back resumes the loop with
   * the arm down; the operator arms again. This is not the latched stop.
   */
  active?: boolean
}

export interface BridgeLink extends RemoLink {
  /** The last session facts the vehicle gave, kept after the link drops. */
  lastSession: SessionFacts | null
}

/**
 * The arm bit on the wire is the operator's arm, and only while this
 * cockpit holds control: Drive active, the operator past the connect step,
 * the link open, and no relinquish since the operator last pressed arm.
 * Telemetry never asserts it.
 */
export function outgoing(cmd: Command, mayArm: boolean): Command {
  return { ...cmd, safety: { arm: mayArm && cmd.safety.arm, estop: cmd.safety.estop } }
}

export function useBridgeTransport(
  password: string | null,
  live: boolean,
  { hz = 15, active = true }: BridgeOptions = {},
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

  // `active` is read through a ref for the same reason as `live`: changing
  // it must never re-create the connection. The connection effect hands
  // back what to do on a change.
  const activeRef = useRef(active)
  const onActiveChange = useRef<((active: boolean) => void) | null>(null)

  useEffect(() => {
    if (!target || !password) return
    const store = useVehicleStore
    const t = new BridgeTransport(target.url, password)

    // True from the moment control is given up (Drive left, or the link
    // lost) until the operator arms again while active on an open link.
    // While true this cockpit never asserts arm, whatever the store or the
    // telemetry says.
    let relinquished = true
    let linkOpen = false
    const mayArm = () => liveRef.current && activeRef.current && linkOpen && !relinquished
    const giveUp = () => {
      relinquished = true
      store.getState().relinquish()
    }

    t.onStatus = (s) => {
      setStatus(s)
      const wasOpen = linkOpen
      linkOpen = s === 'open'
      if (linkOpen) setEverOpen(true)
      else {
        setRole(null)
        setSession(null)
        // Link loss is a relinquish: the new session waits for a fresh arm.
        if (wasOpen) giveUp()
        relinquished = true
      }
      if (s === 'connecting') setAuthFailed(false)
      store.getState().setRemote(linkOpen)
    }
    t.onRole = (r) => setRole(r === 'DRIVER' || r === 'SPECTATOR' ? r : null)
    t.onSession = (facts) => {
      setSession(facts)
      setLastSession(facts)
    }
    t.onAuthFail = () => setAuthFailed(true)
    t.onTelemetry = (tel) => store.getState().applyRemoteTelemetry(tel)
    t.onPreflight = (p) => store.getState().applyPreflight(p)

    onActiveChange.current = (nowActive) => {
      if (nowActive) return // the arm stays down until the operator arms
      giveUp()
      // A cmd frame without arm disarms the daemon's watchdog to STOPPED
      // (no latch). It goes now, not on the next interval.
      t.send(outgoing(store.getState().command, false))
    }

    t.connect()

    const framesPerBeat = Math.max(1, Math.round(hz / 5))
    let n = 0
    const id = setInterval(() => {
      if (activeRef.current) t.send(outgoing(store.getState().command, mayArm()))
      if (++n % framesPerBeat === 0) t.heartbeat()
    }, 1000 / hz)

    // momentary edges must not fall between interval samples
    const unsub = store.subscribe((state, prev) => {
      if (state.command.safety.estop && !prev.command.safety.estop) t.estop()
      else if (state.armPresses !== prev.armPresses && activeRef.current && liveRef.current && linkOpen) {
        relinquished = false // the operator's fresh arm
        t.send(outgoing(state.command, mayArm()))
      }
    })

    const onHide = () => t.close()
    window.addEventListener('pagehide', onHide)
    window.addEventListener('beforeunload', onHide)

    return () => {
      onActiveChange.current = null
      clearInterval(id)
      unsub()
      window.removeEventListener('pagehide', onHide)
      window.removeEventListener('beforeunload', onHide)
      store.getState().setRemote(false)
      t.close()
    }
  }, [target, password, hz])

  // Declared after the connection effect, so on mount the connection
  // exists before the first change is applied.
  useEffect(() => {
    if (activeRef.current === active) return
    activeRef.current = active
    onActiveChange.current?.(active)
  }, [active])

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
