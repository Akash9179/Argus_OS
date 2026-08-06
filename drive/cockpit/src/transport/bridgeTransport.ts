import type { Command, Telemetry } from '../contract'
import type { LinkStatus } from './remoTransport'

/**
 * Client for the ARGUS DRIVE bridge daemon (drive/bridge). JSON over one
 * WebSocket:
 *   out:  {"t":"auth","password"}   first frame, always
 *         {"t":"cmd", ...Command}   the full cockpit command, verbatim
 *         {"t":"hb"}                keepalive between command frames
 *   in:   {"t":"role","role":"DRIVER"|"SPECTATOR"}
 *         {"t":"telemetry", ...Telemetry}   the vehicle's truth, 10 Hz
 *         {"t":"error","reason":"auth"}
 *
 * Safety lives on the VEHICLE (the daemon's watchdog latches on silence or
 * link loss), so this client's only safety duties are: send honestly, send
 * often, and surface the vehicle's telemetry unmodified.
 */
export class BridgeTransport {
  private ws: WebSocket | null = null
  private readonly url: string
  private readonly password: string
  private closedByUser = false
  private authFailed = false
  private retry = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  onStatus?: (s: LinkStatus) => void
  onRole?: (role: string) => void
  onAuthFail?: () => void
  onTelemetry?: (t: Telemetry) => void

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
      this.retry = 0
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
      } else if (msg.t === 'role' && typeof msg.role === 'string') {
        this.onRole?.(msg.role)
      } else if (msg.t === 'telemetry') {
        this.onTelemetry?.(msg as unknown as Telemetry)
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
    const delay = Math.min(5000, 500 * 2 ** this.retry)
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
