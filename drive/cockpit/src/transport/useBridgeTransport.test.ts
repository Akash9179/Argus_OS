/**
 * Leaving Drive relinquishes control (founder decision, 12 Oct 2026).
 *
 * C2 keeps the cockpit frame mounted while the operator works elsewhere.
 * When Drive stops being the active screen, the cockpit drops the arm,
 * zeroes steer and throttle, sends that frame at once, and stops the
 * command loop. Coming back needs a fresh arm by the operator.
 *
 * The arm is a momentary request: it holds only once the vehicle confirms
 * DRIVING, and only while fresh telemetry keeps saying so.
 *
 * The bridge transport is mocked. Nothing here opens a socket.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Command, PreflightState, SafetyState, SessionFacts, Telemetry } from '../contract'

interface Sent {
  cmd: Command
}

const wire = vi.hoisted(() => ({
  sent: [] as Sent[],
  /** What reached the socket, in order: 'cmd', 'close'. */
  log: [] as string[],
  closes: 0,
  beats: 0,
  estops: 0,
  status: null as unknown as (s: string) => void,
  telemetry: null as unknown as (t: Telemetry) => void,
  preflight: null as unknown as (p: PreflightState) => void,
  session: null as unknown as (f: SessionFacts) => void,
  /** Runs inside send(), so a test can make the socket die mid-frame. */
  onSend: null as null | ((cmd: Command) => void),
}))

vi.mock('./bridgeTransport', () => ({
  BridgeTransport: class {
    onStatus?: (s: string) => void
    onTelemetry?: (t: Telemetry) => void
    onPreflight?: (p: PreflightState) => void
    onSession?: (f: SessionFacts) => void
    connect() {
      wire.status = (s) => this.onStatus?.(s)
      wire.telemetry = (t) => this.onTelemetry?.(t)
      wire.preflight = (p) => this.onPreflight?.(p)
      wire.session = (f) => this.onSession?.(f)
      this.onStatus?.('open')
    }
    send(cmd: Command) {
      // a copy: the hook may hand us the store's live object
      wire.sent.push({ cmd: JSON.parse(JSON.stringify(cmd)) })
      wire.log.push(cmd.safety.arm ? 'cmd armed' : 'cmd disarmed')
      wire.onSend?.(cmd)
    }
    heartbeat() {
      wire.beats++
    }
    estop() {
      wire.estops++
    }
    close() {
      wire.closes++
      wire.log.push('close')
    }
  },
}))

import { useBridgeTransport } from './useBridgeTransport'
import { enterFrame, leaveFrame, parentSays, parentSignsOut } from '../embed/testFrame'
import { getDriveKey, setDriveKey } from './auth'
import { ARM_CONFIRM_MS, useVehicleStore } from '../state/store'

const HZ = 10
const TICK_MS = 1000 / HZ
const armed = (f: Sent | undefined) => f?.cmd.safety.arm === true
const st = () => useVehicleStore.getState()
const PASS: PreflightState = { ran: true, pass: true, checks: [{ name: 'mcu', ok: true, detail: '' }] }
const FAIL: PreflightState = { ran: true, pass: false, checks: [{ name: 'mcu', ok: false, detail: '' }] }

/** One telemetry frame from the vehicle, through the link. */
function reading(safetyState: SafetyState, over: Partial<Telemetry> = {}) {
  act(() => wire.telemetry({ ...st().telemetry, ignition: true, safetyState, ...over }))
}

/** Ignition on, self-test passed, the vehicle at rest. */
function ready() {
  act(() => wire.preflight(PASS))
  reading('STOPPED')
}

const driving = () => reading('DRIVING')

/** Advance time while the vehicle keeps reporting the given state at 10 Hz. */
function steady(state: SafetyState, ticks: number) {
  for (let i = 0; i < ticks; i++) {
    act(() => vi.advanceTimersByTime(TICK_MS))
    reading(state)
  }
}

function bridge() {
  return renderHook(() => useBridgeTransport('pw', true, { hz: HZ }))
}

beforeEach(() => {
  vi.useFakeTimers()
  wire.sent = []
  wire.log = []
  wire.closes = 0
  wire.beats = 0
  wire.estops = 0
  wire.onSend = null
  st().reset()
  window.history.replaceState(null, '', '/?bridge=localhost:8090')
})

afterEach(() => {
  vi.useRealTimers()
  window.history.replaceState(null, '', '/')
})

describe('leaving Drive', () => {
  beforeEach(() => {
    enterFrame()
    parentSays(true)
  })
  afterEach(leaveFrame)

  it('drops the arm, zeroes the command, sends one frame at once, and stops the loop', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    act(() => st().setStick(0.5, 0.7))
    wire.sent = []
    steady('DRIVING', 3)
    expect(wire.sent.length).toBe(3)
    expect(wire.sent.at(-1)).toMatchObject({ cmd: { steer: 0.5, throttle: 0.7, safety: { arm: true } } })

    wire.sent = []
    act(() => parentSays(false))

    // one frame, sent now, not on the next interval
    expect(wire.sent.length).toBe(1)
    expect(wire.sent[0].cmd).toMatchObject({ steer: 0, throttle: 0, safety: { arm: false, estop: false } })
    const store = st().command
    expect(store.steer).toBe(0)
    expect(store.throttle).toBe(0)
    expect(store.safety.arm).toBe(false)

    // and then nothing more on the command channel, though the link stays measured
    const beatsBefore = wire.beats
    steady('STOPPED', 30)
    expect(wire.sent.length).toBe(1)
    expect(wire.beats).toBeGreaterThan(beatsBefore)
    // the latched stop is not how we leave
    expect(wire.estops).toBe(0)
  })

  it('revokes in the same turn as the message, before any React render', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    wire.sent = []

    // no act(): no effect or render may run between these lines
    parentSays(false)
    expect(wire.sent.length).toBe(1)
    expect(armed(wire.sent[0])).toBe(false)
    st().arm()
    expect(st().command.safety.arm).toBe(false)
    vi.advanceTimersByTime(TICK_MS * 3)
    expect(wire.sent.length).toBe(1)
  })

  it('resumes the loop on return, but the arm stays down until the operator arms', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS))
    act(() => parentSays(false))
    wire.sent = []

    // telemetry still reads DRIVING: it must not re-arm the vehicle by itself
    driving()
    act(() => parentSays(true))
    steady('DRIVING', 3)
    expect(wire.sent.length).toBe(3)
    expect(wire.sent.some(armed)).toBe(false)

    // the operator arms: the arm goes out, then the loop asserts it again
    act(() => st().arm())
    expect(armed(wire.sent.at(-1))).toBe(true)
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(armed(wire.sent.at(-1))).toBe(true)
  })

  it('ignores an arm pressed while Drive is not the active screen', () => {
    act(() => parentSays(false))
    bridge()
    ready()
    act(() => st().arm())
    steady('STOPPED', 5)
    expect(wire.sent.length).toBe(0)
  })

  it('still sends STOP while Drive is hidden', () => {
    act(() => parentSays(false))
    bridge()
    act(() => st().estop())
    expect(wire.estops).toBe(1)
  })

  it('stays relinquished when the link dies during the relinquish frame', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    // the socket closes as the neutral frame goes out
    wire.onSend = (cmd) => {
      if (!cmd.safety.arm) {
        wire.onSend = null
        wire.status('closed')
      }
    }
    act(() => parentSays(false))
    expect(st().command.safety.arm).toBe(false)

    act(() => wire.status('connecting'))
    act(() => wire.status('open'))
    act(() => parentSays(true))
    wire.sent = []
    // the vehicle's state from before the drop must not re-arm anything
    ready()
    steady('DRIVING', 5)
    expect(wire.sent.length).toBe(5)
    expect(wire.sent.some(armed)).toBe(false)
    expect(st().command.safety.arm).toBe(false)
  })
})

describe('a standalone cockpit', () => {
  it('keeps the loop live and asserts a confirmed arm', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    wire.sent = []
    steady('DRIVING', 2)
    expect(wire.sent.length).toBe(2)
    expect(wire.sent.every(armed)).toBe(true)
  })
})

describe('an embedded cockpit', () => {
  beforeEach(() => {
    enterFrame()
  })
  afterEach(leaveFrame)

  it('sends no command frames before the first active message', () => {
    bridge()
    ready()
    steady('DRIVING', 10)
    expect(wire.sent.length).toBe(0)

    act(() => parentSays(true))
    steady('DRIVING', 2)
    expect(wire.sent.length).toBe(2)
    // a fresh embed starts with the arm down
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('listens only to its parent window', () => {
    bridge()
    ready()
    const stranger = document.createElement('iframe')
    document.body.appendChild(stranger)
    act(() => parentSays(true, stranger.contentWindow!))
    steady('STOPPED', 5)
    expect(wire.sent.length).toBe(0)
    stranger.remove()
  })

  it('listens only to the origin of the page that framed it', () => {
    bridge()
    ready()
    act(() => parentSays(true, window.parent, 'http://evil.test'))
    steady('STOPPED', 5)
    expect(wire.sent.length).toBe(0)
    act(() => parentSays(true))
    steady('STOPPED', 2)
    expect(wire.sent.length).toBe(2)
  })
})

describe('the arm bit on the wire', () => {
  it('never carries an arm pressed while Drive was hidden, until a fresh arm while active', () => {
    enterFrame()
    try {
      act(() => parentSays(false))
      bridge()
      ready()
      // the gamepad keeps polling while Drive is hidden
      act(() => st().arm())
      act(() => parentSays(true))
      steady('STOPPED', 5)
      expect(wire.sent.length).toBe(5)
      expect(wire.sent.some(armed)).toBe(false)

      act(() => st().arm())
      driving()
      steady('DRIVING', 3)
      expect(wire.sent.slice(5).length).toBeGreaterThan(0)
      expect(wire.sent.slice(5).every(armed)).toBe(true)
    } finally {
      leaveFrame()
    }
  })

  it('drops the arm when the link drops, and does not re-arm on reconnect', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(armed(wire.sent.at(-1))).toBe(true)

    act(() => wire.status('closed'))
    expect(st().command.safety.arm).toBe(false)
    // the local sim takes over the display and still reads DRIVING
    act(() => st().tick(0.05))
    act(() => wire.status('connecting'))
    act(() => wire.status('open'))
    wire.sent = []
    driving()
    steady('DRIVING', 5)
    expect(wire.sent.length).toBe(5)
    expect(wire.sent.some(armed)).toBe(false)

    act(() => st().arm())
    expect(armed(wire.sent.at(-1))).toBe(true)
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(armed(wire.sent.at(-1))).toBe(true)
  })

  it('ignores an arm pressed while the link is down', () => {
    bridge()
    ready()
    act(() => wire.status('closed'))
    act(() => st().arm())
    act(() => wire.status('open'))
    wire.sent = []
    ready()
    steady('STOPPED', 3)
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('keeps asserting a fresh arm while telemetry lags, inside the confirm window', () => {
    bridge()
    ready()
    act(() => st().arm())
    // telemetry has not caught up: the daemon must not see arm=false
    steady('STOPPED', 3)
    driving()
    steady('DRIVING', 2)
    expect(wire.sent.length).toBe(1 + 5)
    expect(wire.sent.every(armed)).toBe(true)

    // STOP ends it
    act(() => st().estop())
    wire.sent = []
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('stops asserting the arm when the vehicle reports it left DRIVING', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS))
    reading('LATCHED')
    wire.sent = []
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('stops asserting the arm on a STOPPED reading after confirmation', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    reading('STOPPED')
    wire.sent = []
    steady('STOPPED', 3)
    expect(wire.sent.some(armed)).toBe(false)
  })
})

describe('an arm request', () => {
  it('refused by a failed self-test never arms when the self-test later passes', () => {
    bridge()
    act(() => wire.preflight(FAIL))
    reading('STOPPED')
    // the gamepad arm combo, at neutral: the button is disabled, the pad is not
    act(() => st().arm())
    steady('STOPPED', 3)
    expect(wire.sent.some(armed)).toBe(false)

    // ignition cycled: the self-test now passes, and the operator is on the throttle
    act(() => wire.preflight(PASS))
    act(() => st().setStick(0, 0.6))
    steady('STOPPED', 10)
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('expires when the vehicle never confirms it, and the operator must press again', () => {
    bridge()
    ready()
    act(() => st().arm())
    wire.sent = []
    steady('STOPPED', ARM_CONFIRM_MS / TICK_MS + 2)
    // armed frames only inside the window, then none
    const last = wire.sent.slice(-2)
    expect(last.some(armed)).toBe(false)
    expect(wire.sent.filter(armed).length).toBeLessThanOrEqual(ARM_CONFIRM_MS / TICK_MS)
    expect(st().command.safety.arm).toBe(false)
  })
})

describe('telemetry freshness', () => {
  it('a stalled open socket relinquishes after the default window and needs a fresh arm', () => {
    bridge()
    ready()
    act(() => st().arm())
    driving()
    steady('DRIVING', 2)
    expect(armed(wire.sent.at(-1))).toBe(true)

    // telemetry stops; the socket says nothing
    wire.sent = []
    act(() => vi.advanceTimersByTime(1000 + TICK_MS * 2))
    expect(st().command.safety.arm).toBe(false)
    expect(st().remote).toBe(false)
    expect(armed(wire.sent.at(-1))).toBe(false)

    // traffic resumes: no arm until the operator presses again
    wire.sent = []
    steady('LATCHED', 5)
    expect(st().remote).toBe(true)
    expect(wire.sent.some(armed)).toBe(false)
  })

  it("uses the vehicle's declared watchdog window", () => {
    bridge()
    act(() => wire.session({ role: 'DRIVER', driver: 'a', vehicle: null, watchdogMs: 700, since: 0 }))
    ready()
    act(() => st().arm())
    driving()
    act(() => vi.advanceTimersByTime(600))
    expect(armed(wire.sent.at(-1))).toBe(true)
    act(() => vi.advanceTimersByTime(200))
    expect(st().command.safety.arm).toBe(false)
    expect(armed(wire.sent.at(-1))).toBe(false)
  })

  it('counts the link live only once telemetry arrives after the socket opens', () => {
    const { result } = bridge()
    expect(st().remote).toBe(false)
    expect(result.current.everOpen).toBe(false)
    reading('STOPPED')
    expect(st().remote).toBe(true)
    expect(result.current.everOpen).toBe(true)

    act(() => wire.status('closed'))
    act(() => wire.status('connecting'))
    act(() => wire.status('open'))
    expect(st().remote).toBe(false)
    reading('STOPPED')
    expect(st().remote).toBe(true)
  })
})

describe('sign-out from C2', () => {
  beforeEach(() => {
    enterFrame()
    parentSays(true)
  })
  afterEach(leaveFrame)

  it('disarms, forgets the key, and closes the socket cleanly, in the same turn', () => {
    setDriveKey('operator-a')
    bridge()
    ready()
    act(() => st().arm())
    driving()
    wire.log = []

    // no act(): all three happen before anything else can run
    parentSignsOut()
    expect(wire.log).toEqual(['cmd disarmed', 'close'])
    expect(st().command.safety.arm).toBe(false)
    expect(getDriveKey()).toBeNull()

    // nothing more goes out
    vi.advanceTimersByTime(TICK_MS * 5)
    expect(wire.log).toEqual(['cmd disarmed', 'close'])
  })

  it('is heard only from the parent at its own origin', () => {
    setDriveKey('operator-a')
    bridge()
    parentSignsOut(window.parent, 'http://evil.test')
    expect(getDriveKey()).toBe('operator-a')
    expect(wire.closes).toBe(0)
  })
})

describe('ignition across a reconnect', () => {
  it('is not replayed: the operator turns it on again', () => {
    bridge()
    ready()
    act(() => st().toggleIgnition())
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(wire.sent.at(-1)?.cmd.aux.ignition).toBe(true)

    act(() => wire.status('closed'))
    act(() => wire.status('connecting'))
    act(() => wire.status('open'))
    wire.sent = []
    reading('STOPPED')
    steady('STOPPED', 5)
    expect(wire.sent.length).toBe(5)
    expect(wire.sent.some((f) => f.cmd.aux.ignition)).toBe(false)

    act(() => st().toggleIgnition())
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(wire.sent.at(-1)?.cmd.aux.ignition).toBe(true)
  })
})
