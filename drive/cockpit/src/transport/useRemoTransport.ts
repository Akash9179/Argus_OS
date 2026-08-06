import { useEffect, useMemo, useRef, useState } from 'react'
import { useVehicleStore } from '../state/store'
import { RemoTransport, type LinkStatus } from './remoTransport'

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

export function useRemoTransport(password: string | null, live: boolean, hz = 20): RemoLink {
  const target = useMemo(() => parseDriveParam(), [])
  const [status, setStatus] = useState<LinkStatus>('connecting')
  const [role, setRole] = useState<DriveRole>(null)
  const [authFailed, setAuthFailed] = useState(false)

  // `live` gates actuation without re-creating the connection: until the operator
  // has passed the connect modal, the vehicle is held at neutral even if a gamepad
  // is moving the stick. Read via ref so toggling it never triggers a reconnect.
  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  }, [live])

  useEffect(() => {
    if (!target || !password) return
    const t = new RemoTransport(target.url, password)
    t.onStatus = (s) => {
      setStatus(s)
      // each (re)connection attempt starts with a clean role/auth slate
      if (s === 'connecting') {
        setRole(null)
        setAuthFailed(false)
      }
    }
    t.onRole = (r) => setRole(r === 'DRIVER' || r === 'SPECTATOR' ? r : null)
    t.onAuthFail = () => setAuthFailed(true)
    t.connect()

    let beat = 0
    const id = setInterval(() => {
      const s = useVehicleStore.getState()
      t.update({
        steer: s.command.steer,
        throttle: s.command.throttle,
        gear: s.command.gear,
        driving: liveRef.current && s.telemetry.safetyState === 'DRIVING',
      })
      // heartbeat ~5x/s so the relay dead-man can distinguish steady-state from a
      // stalled link (drive tokens only fire on change, so silence != alive)
      if (++beat % Math.max(1, Math.round(hz / 5)) === 0) t.heartbeat()
    }, 1000 / hz)

    const unsub = useVehicleStore.subscribe((state, prev) => {
      if (state.command.safety.estop && !prev.command.safety.estop) t.estop()
    })

    const onHide = () => t.close()
    window.addEventListener('pagehide', onHide)
    window.addEventListener('beforeunload', onHide)

    return () => {
      clearInterval(id)
      unsub()
      window.removeEventListener('pagehide', onHide)
      window.removeEventListener('beforeunload', onHide)
      t.close()
    }
  }, [target, password, hz])

  return { active: !!target, label: target?.label ?? '', status, role, authFailed }
}
