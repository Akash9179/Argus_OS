import { useEffect, useMemo, useRef, useState } from 'react'
import { useVehicleStore } from '../state/store'
import { RemoTransport, type LinkStatus } from './remoTransport'
import type { SessionFacts } from '../contract'

/**
 * Opt-in live transport. Activated by a URL param so the deployed/mock app is
 * untouched:  ?drive=<host>[:port]   e.g.  ?drive=100.81.28.60:8080
 *
 * Scheme is inferred from the page: an https page (Vercel) connects over wss://,
 * a local http page over ws://. A full ws://… / wss://… value is also accepted.
 *
 * When live it taps the SAME command the mock consumes and streams Remo tokens
 * at 20 Hz, reusing the store's safety state machine: any non-DRIVING state
 * (E-STOP / latched) collapses output to neutral. A password (if required by the
 * relay) is sent on every (re)connect; without one the transport stays idle.
 */
export type DriveRole = 'DRIVER' | 'SPECTATOR' | null

export interface RemoLink {
  active: boolean
  label: string
  status: LinkStatus
  role: DriveRole
  authFailed: boolean
  /** The bridge's session facts; a Remo link has none. */
  session?: SessionFacts | null
  /** Command frames per second this link sends while open. */
  hz?: number
  /** True once this link has been open at least once. */
  everOpen?: boolean
}

interface DriveTarget {
  url: string
  label: string
}

function parseDriveParam(): DriveTarget | null {
  if (typeof window === 'undefined') return null
  const raw = new URLSearchParams(window.location.search).get('drive')
  if (!raw) return null
  if (/^wss?:\/\//.test(raw)) {
    const base = raw.replace(/\/$/, '')
    return { url: base.endsWith('/ws') ? base : base + '/ws', label: raw }
  }
  const https = window.location.protocol === 'https:'
  // default port: 8080 for local ws, none (443) behind an https tunnel
  const hostport = raw.includes(':') ? raw : https ? raw : `${raw}:8080`
  const scheme = https ? 'wss' : 'ws'
  return { url: `${scheme}://${hostport}/ws`, label: hostport }
}

export interface RemoOptions {
  /** Drive frames per second while Drive is active. */
  hz?: number
  /**
   * Whether Drive is the operator's active screen. Leaving it sends neutral
   * at once and stops drive updates; heartbeats continue. Coming back needs
   * a fresh arm by the operator. Same rule as the bridge link.
   */
  active?: boolean
}

export function useRemoTransport(
  password: string | null,
  live: boolean,
  { hz = 20, active = true }: RemoOptions = {},
): RemoLink {
  const target = useMemo(() => parseDriveParam(), [])
  const [status, setStatus] = useState<LinkStatus>('connecting')
  const [role, setRole] = useState<DriveRole>(null)
  const [authFailed, setAuthFailed] = useState(false)
  const [everOpen, setEverOpen] = useState(false)

  // `live` gates actuation without re-creating the connection: until the operator
  // has passed the connect modal, the vehicle is held at neutral even if a gamepad
  // is moving the stick. Read via ref so toggling it never triggers a reconnect.
  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  }, [live])

  const activeRef = useRef(active)
  const onActiveChange = useRef<((active: boolean) => void) | null>(null)

  useEffect(() => {
    if (!target || !password) return
    const store = useVehicleStore
    const t = new RemoTransport(target.url, password)

    // True from giving up control (Drive left, or the link lost) until the
    // operator arms again while active on an open link. Same rule as the
    // bridge link: the local sim's DRIVING alone never drives.
    let relinquished = true
    let linkOpen = false

    t.onStatus = (s) => {
      setStatus(s)
      const wasOpen = linkOpen
      linkOpen = s === 'open'
      if (linkOpen) setEverOpen(true)
      else {
        if (wasOpen) store.getState().relinquish()
        relinquished = true
      }
      // each (re)connection attempt starts with a clean role/auth slate
      if (s === 'connecting') {
        setRole(null)
        setAuthFailed(false)
      }
    }
    t.onRole = (r) => setRole(r === 'DRIVER' || r === 'SPECTATOR' ? r : null)
    t.onAuthFail = () => setAuthFailed(true)

    onActiveChange.current = (nowActive) => {
      if (nowActive) return
      relinquished = true
      store.getState().relinquish()
      const { gear } = store.getState().command
      t.update({ steer: 0, throttle: 0, gear, driving: false })
    }

    t.connect()

    let beat = 0
    const id = setInterval(() => {
      const s = store.getState()
      if (activeRef.current)
        t.update({
          steer: s.command.steer,
          throttle: s.command.throttle,
          gear: s.command.gear,
          driving:
            liveRef.current &&
            linkOpen &&
            !relinquished &&
            s.command.safety.arm &&
            s.telemetry.safetyState === 'DRIVING',
        })
      // heartbeat ~5x/s so the relay dead-man can distinguish steady-state from a
      // stalled link (drive tokens only fire on change, so silence != alive)
      if (++beat % Math.max(1, Math.round(hz / 5)) === 0) t.heartbeat()
    }, 1000 / hz)

    const unsub = store.subscribe((state, prev) => {
      if (state.command.safety.estop && !prev.command.safety.estop) t.estop()
      else if (state.armPresses !== prev.armPresses && activeRef.current && liveRef.current && linkOpen)
        relinquished = false
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
      t.close()
    }
  }, [target, password, hz])

  useEffect(() => {
    if (activeRef.current === active) return
    activeRef.current = active
    onActiveChange.current?.(active)
  }, [active])

  return { active: !!target, label: target?.label ?? '', status, role, authFailed, everOpen }
}
