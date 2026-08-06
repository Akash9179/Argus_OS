import { TokenEmitter, type DriveInput } from './tokens'

export type LinkStatus = 'connecting' | 'open' | 'closed' | 'error'

/**
 * Browser-side bridge to the existing Remo Go server. The browser's native
 * WebSocket handles framing/masking; Remo appends '\n' and writes each token
 * straight to the Arduino serial port. We are a plain WS client of /ws — same
 * seam the Remo web UI uses (see ARGUS_INTEGRATION_NOTES.md §7).
 *
 * Auto-reconnects with capped exponential backoff so a transient drop (Tailscale
 * blip, Remo restart, sleep/wake) recovers without a page reload. NOTE: a dropped
 * link does NOT stop the vehicle — the Arduino holds its last command (no firmware
 * failsafe). Loss-of-link safety belongs in an on-vehicle watchdog (real product).
 *
 * THROWAWAY-grade transport for bench/UI testing.
 */
export class RemoTransport {
  private ws: WebSocket | null = null
  private emitter = new TokenEmitter()
  private readonly url: string
  private readonly password: string
  private closedByUser = false
  private authFailed = false
  private retry = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  onStatus?: (s: LinkStatus) => void
  /** role granted by the relay: 'DRIVER' (you actuate) or 'SPECTATOR' (view only) */
  onRole?: (role: string) => void
  /** the relay rejected the password */
  onAuthFail?: () => void

  /** url is a full ws:// or wss:// endpoint (built by the hook from ?drive=).
   *  password is sent as the first frame (`AUTH:<pw>`) so the relay can gate
   *  access; ignored by a bare Remo server, which has no auth. */
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
      // Authenticate first, before any drive token reaches the relay.
      if (this.password) ws.send('AUTH:' + this.password)
      // Fresh emitter so the next tick re-asserts the CURRENT command after a
      // reconnect (cached neutral would otherwise suppress the first tokens).
      this.emitter = new TokenEmitter()
      this.onStatus?.('open')
    }
    ws.onmessage = (e) => {
      const m = String(e.data)
      if (m === 'AUTH:FAIL') {
        this.authFailed = true // stop reconnecting with a known-bad password
        this.onAuthFail?.()
      } else if (m.startsWith('ROLE:')) {
        this.onRole?.(m.slice(5))
      }
      // anything else is vehicle telemetry — ignored for now
    }
    ws.onclose = () => {
      this.onStatus?.('closed')
      if (!this.closedByUser) this.scheduleReconnect()
    }
    ws.onerror = () => {
      this.onStatus?.('error')
      // onclose follows and drives the reconnect.
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

  private raw(tokens: string[]): void {
    const ws = this.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    for (const t of tokens) ws.send(t)
  }

  /** Send only the tokens that changed for this drive input. */
  update(i: DriveInput): void {
    this.raw(this.emitter.update(i))
  }

  /** Keepalive so the relay's dead-man can tell a healthy steady link (no token
   *  changes) from a stalled one. Never reaches the Arduino. */
  heartbeat(): void {
    this.raw(['HB'])
  }

  /** Immediate full neutral (E-STOP). */
  estop(): void {
    this.raw(this.emitter.forceNeutral())
  }

  /** Neutral then close — for unmount / page unload. Stops reconnecting. */
  close(): void {
    this.closedByUser = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.raw(this.emitter.forceNeutral())
    try {
      this.ws?.close()
    } catch {
      /* ignore */
    }
    this.ws = null
  }
}
