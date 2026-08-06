import { useEffect, useMemo, useRef, useState } from 'react'
import { useVehicleStore } from '../state/store'
import { BridgeTransport } from './bridgeTransport'
import type { LinkStatus } from './remoTransport'
import type { DriveRole, RemoLink } from './useRemoTransport'

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

export function useBridgeTransport(password: string | null, live: boolean, hz = 15): RemoLink {
  const target = useMemo(() => parseBridgeParam(), [])
  const [status, setStatus] = useState<LinkStatus>('connecting')
  const [role, setRole] = useState<DriveRole>(null)
  const [authFailed, setAuthFailed] = useState(false)

  const liveRef = useRef(live)
  useEffect(() => {
    liveRef.current = live
  }, [live])

  useEffect(() => {
    if (!target || !password) return
    const store = useVehicleStore
    const t = new BridgeTransport(target.url, password)
    t.onStatus = (s) => {
      setStatus(s)
      if (s === 'connecting') {
        setRole(null)
        setAuthFailed(false)
      }
      store.getState().setRemote(s === 'open')
    }
    t.onRole = (r) => setRole(r === 'DRIVER' || r === 'SPECTATOR' ? r : null)
    t.onAuthFail = () => setAuthFailed(true)
    t.onTelemetry = (tel) => store.getState().applyRemoteTelemetry(tel)
    t.onPreflight = (p) => store.getState().applyPreflight(p)
    t.connect()

    const framesPerBeat = Math.max(1, Math.round(hz / 5))
    let n = 0
    const id = setInterval(() => {
      const s = store.getState()
      const driving = liveRef.current && s.telemetry.safetyState === 'DRIVING'
      t.send(s.command, driving)
      if (++n % framesPerBeat === 0) t.heartbeat()
    }, 1000 / hz)

    // momentary edges must not fall between interval samples
    const unsub = store.subscribe((state, prev) => {
      if (state.command.safety.estop && !prev.command.safety.estop) t.estop()
      else if (state.command.safety.arm && !prev.command.safety.arm)
        t.send(state.command, false)
    })

    const onHide = () => t.close()
    window.addEventListener('pagehide', onHide)
    window.addEventListener('beforeunload', onHide)

    return () => {
      clearInterval(id)
      unsub()
      window.removeEventListener('pagehide', onHide)
      window.removeEventListener('beforeunload', onHide)
      store.getState().setRemote(false)
      t.close()
    }
  }, [target, password, hz])

  return { active: !!target, label: target?.label ?? '', status, role, authFailed }
}
