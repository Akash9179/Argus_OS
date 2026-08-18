import type { Command, PreflightState, Telemetry } from '../contract'
import type { LinkStatus } from './remoTransport'

/**
 * Client for the ARGUS DRIVE bridge daemon (drive/bridge). JSON over one
 * WebSocket:
 *   out:  {"t":"auth","password"}   first frame, always
 *         {"t":"cmd", ...Command}   the full cockpit command, verbatim
 *         {"t":"hb"}                keepalive between command frames
 *   in:   {"t":"role","role":"DRIVER"|"SPECTATOR"}
 *         {"t":"telemetry", ...Telemetry}   the vehicle's truth, 10 Hz
 *         {"t":"error","reason":"auth"}          bad token: stop, tell the user
 *         {"t":"error","reason":"rate_limited"}  locked out: wait, then retry
 *
 * Safety lives on the VEHICLE (the daemon's watchdog latches on silence or
 * link loss), so this client's only safety duties are: send honestly, send
 * often, and surface the vehicle's telemetry unmodified.
 */

// How long to hold off after the daemon says rate_limited. The daemon's
// lockout window defaults to 60s; retrying at this pace heals the session
// soon after it expires without hammering the locked door in the meantime.
const RATE_LIMIT_HOLD_MS = 15_000

export class BridgeTransport {
  private ws: WebSocket | null = null
  private readonly url: string
  private readonly password: string
  private closedByUser = false
  private authFailed = false
  private retry = 0
  private holdMs = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  onStatus?: (s: LinkStatus) => void
  onRole?: (role: string) => void
  onAuthFail?: () => void
  onRateLimited?: () => void
  onTelemetry?: (t: Telemetry) => void
  onPreflight?: (p: PreflightState) => void

  constructor(url: string, password = '') {
    this.url = url
    this.password = password
  }

  connect(): void {
    this.closedByUser = false
    this.open()
  }

  private open(): void {
    this.onStatus?.('connecting')
    let ws: WebSocket
    try {
      ws = new WebSocket(this.url)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.ws = ws
    ws.onopen = () => {
      // retry is NOT reset here: the socket opening says nothing about
      // whether the daemon will let us in. It resets when a role arrives,
      // so a lockout keeps its growing backoff instead of hammering at
      // the floor delay forever.
      ws.send(JSON.stringify({ t: 'auth', password: this.password }))
      this.onStatus?.('open')
    }
    ws.onmessage = (e) => {
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(String(e.data))
      } catch {
        return
      }
      if (msg.t === 'error' && msg.reason === 'auth') {
        this.authFailed = true
        this.onAuthFail?.()
      } else if (msg.t === 'error' && msg.reason === 'rate_limited') {
        // Not a bad token: the daemon locked this address out for a
        // while. Hold the next attempt back so the lockout can expire
        // instead of being refreshed by our own retries.
        this.holdMs = RATE_LIMIT_HOLD_MS
        this.onRateLimited?.()
      } else if (msg.t === 'role' && typeof msg.role === 'string') {
        this.retry = 0
        this.holdMs = 0
        this.onRole?.(msg.role)
      } else if (msg.t === 'telemetry') {
        this.onTelemetry?.(msg as unknown as Telemetry)
      } else if (msg.t === 'preflight') {
        this.onPreflight?.(msg as unknown as PreflightState)
      }
    }
    ws.onclose = () => {
      this.onStatus?.('closed')
      if (!this.closedByUser) this.scheduleReconnect()
    }
    ws.onerror = () => {
      this.onStatus?.('error')
    }
  }

  private scheduleReconnect(): void {
    if (this.closedByUser || this.authFailed || this.reconnectTimer) return
    const delay = Math.max(this.holdMs, Math.min(5000, 500 * 2 ** this.retry))
    this.holdMs = 0
    this.retry++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.open()
    }, delay)
  }

  private raw(obj: Record<string, unknown>): void {
    const ws = this.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify(obj))
  }

  /** Send the full command frame. `driving` asserts continuous arm intent
   *  (the daemon disarms the moment a frame arrives without it). */
  send(cmd: Command, driving: boolean): void {
    this.raw({
      t: 'cmd',
      ...cmd,
      safety: { arm: driving || cmd.safety.arm, estop: cmd.safety.estop },
    })
  }

  heartbeat(): void {
    this.raw({ t: 'hb' })
  }

  /** Immediate E-STOP frame: neutral drive, estop asserted. */
  estop(): void {
    this.raw({
      t: 'cmd',
      steer: 0,
      throttle: 0,
      gear: 'N',
      mode: 'MANUAL',
      aux: { ignition: false, headlights: false, blinker: 'hazard', horn: false, record: true },
      safety: { arm: false, estop: true },
    })
  }

  close(): void {
    this.closedByUser = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    try {
      this.ws?.close()
    } catch {
      /* ignore */
    }
    this.ws = null
  }
}
