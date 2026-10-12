import { useEffect, useMemo, useRef, useState } from 'react'
import { useVehicleStore } from '../state/store'
import { BridgeTransport } from './bridgeTransport'
import type { LinkStatus } from './remoTransport'
import type { DriveRole, RemoLink } from './useRemoTransport'
import type { SessionFacts } from '../contract'

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

export function useBridgeTransport(
  password: string | null,
  live: boolean,
  { hz = 15, active = true }: BridgeOptions = {},
): RemoLink {
  const target = useMemo(() => parseBridgeParam(), [])
  const [status, setStatus] = useState<LinkStatus>('connecting')
  const [role, setRole] = useState<DriveRole>(null)
  const [authFailed, setAuthFailed] = useState(false)
  const [session, setSession] = useState<SessionFacts | null>(null)

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
    t.onStatus = (s) => {
      setStatus(s)
      if (s === 'connecting') {
        setRole(null)
        setSession(null)
        setAuthFailed(false)
      }
      store.getState().setRemote(s === 'open')
    }
    t.onRole = (r) => setRole(r === 'DRIVER' || r === 'SPECTATOR' ? r : null)
    t.onSession = setSession
    t.onAuthFail = () => setAuthFailed(true)
    t.onTelemetry = (tel) => store.getState().applyRemoteTelemetry(tel)
    t.onPreflight = (p) => store.getState().applyPreflight(p)
    t.connect()

    // True from the moment Drive is left until the operator arms again.
    // While true this cockpit never asserts arm, whatever the telemetry
    // says: a DRIVING reading that arrives late must not re-arm.
    let relinquished = !activeRef.current
    onActiveChange.current = (nowActive) => {
      if (nowActive) return // the arm stays down until the operator arms
      relinquished = true
      store.getState().relinquish()
      // A cmd frame without arm disarms the daemon's watchdog to STOPPED
      // (no latch). It goes now, not on the next interval.
      t.send(store.getState().command, false)
    }

    const framesPerBeat = Math.max(1, Math.round(hz / 5))
    let n = 0
    const id = setInterval(() => {
      if (activeRef.current) {
        const s = store.getState()
        const driving = liveRef.current && !relinquished && s.telemetry.safetyState === 'DRIVING'
        t.send(s.command, driving)
      }
      if (++n % framesPerBeat === 0) t.heartbeat()
    }, 1000 / hz)

    // momentary edges must not fall between interval samples
    const unsub = store.subscribe((state, prev) => {
      if (state.command.safety.estop && !prev.command.safety.estop) t.estop()
      else if (state.command.safety.arm && !prev.command.safety.arm && activeRef.current) {
        relinquished = false // the operator's fresh arm
        t.send(state.command, false)
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

  return { active: !!target, label: target?.label ?? '', status, role, authFailed, session, hz }
}
