/**
 * Leaving Drive relinquishes control (founder decision, 12 Oct 2026).
 *
 * C2 keeps the cockpit frame mounted while the operator works elsewhere.
 * When Drive stops being the active screen, the cockpit drops the arm,
 * zeroes steer and throttle, sends that frame at once, and stops the
 * command loop. Coming back needs a fresh arm by the operator.
 *
 * The bridge transport is mocked. Nothing here opens a socket.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Command } from '../contract'

interface Sent {
  cmd: Command
}

const wire = vi.hoisted(() => ({
  sent: [] as Sent[],
  beats: 0,
  estops: 0,
  status: null as unknown as (s: string) => void,
}))

vi.mock('./bridgeTransport', () => ({
  BridgeTransport: class {
    onStatus?: (s: string) => void
    connect() {
      wire.status = (s) => this.onStatus?.(s)
      this.onStatus?.('open')
    }
    send(cmd: Command) {
      // a copy: the hook may hand us the store's live object
      wire.sent.push({ cmd: JSON.parse(JSON.stringify(cmd)) })
    }
    heartbeat() {
      wire.beats++
    }
    estop() {
      wire.estops++
    }
    close() {}
  },
}))

import { useBridgeTransport } from './useBridgeTransport'
import { forgetDriveActive, useDriveActive } from '../embed/driveActive'
import { useVehicleStore } from '../state/store'

const HZ = 10
const TICK_MS = 1000 / HZ
const armed = (f: Sent | undefined) => f?.cmd.safety.arm === true

function driving() {
  const s = useVehicleStore.getState()
  s.applyRemoteTelemetry({ ...s.telemetry, safetyState: 'DRIVING' })
}

beforeEach(() => {
  vi.useFakeTimers()
  wire.sent = []
  wire.beats = 0
  wire.estops = 0
  useVehicleStore.getState().reset()
  window.history.replaceState(null, '', '/?bridge=localhost:8090')
})

afterEach(() => {
  vi.useRealTimers()
  window.history.replaceState(null, '', '/')
})

describe('leaving Drive', () => {
  it('drops the arm, zeroes the command, sends one frame at once, and stops the loop', () => {
    const { rerender } = renderHook(
      ({ active }) => useBridgeTransport('pw', true, { hz: HZ, active }),
      { initialProps: { active: true } },
    )
    act(() => useVehicleStore.getState().arm())
    driving()
    act(() => useVehicleStore.getState().setStick(0.5, 0.7))
    wire.sent = []
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.sent.length).toBe(3)
    expect(wire.sent.at(-1)).toMatchObject({ cmd: { steer: 0.5, throttle: 0.7, safety: { arm: true } } })

    wire.sent = []
    rerender({ active: false })

    // one frame, sent now, not on the next interval
    expect(wire.sent.length).toBe(1)
    expect(wire.sent[0].cmd).toMatchObject({ steer: 0, throttle: 0, safety: { arm: false, estop: false } })
    const store = useVehicleStore.getState().command
    expect(store.steer).toBe(0)
    expect(store.throttle).toBe(0)
    expect(store.safety.arm).toBe(false)

    // and then nothing more on the command channel, though the link stays measured
    const beatsBefore = wire.beats
    act(() => vi.advanceTimersByTime(TICK_MS * 30))
    expect(wire.sent.length).toBe(1)
    expect(wire.beats).toBeGreaterThan(beatsBefore)
    // the latched stop is not how we leave
    expect(wire.estops).toBe(0)
  })

  it('resumes the loop on return, but the arm stays down until the operator arms', () => {
    const { rerender } = renderHook(
      ({ active }) => useBridgeTransport('pw', true, { hz: HZ, active }),
      { initialProps: { active: true } },
    )
    act(() => useVehicleStore.getState().arm())
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS))
    rerender({ active: false })
    wire.sent = []

    // telemetry still reads DRIVING: it must not re-arm the vehicle by itself
    driving()
    rerender({ active: true })
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.sent.length).toBe(3)
    expect(wire.sent.some(armed)).toBe(false)

    // the operator arms: the arm goes out, then the loop asserts it again
    act(() => useVehicleStore.getState().arm())
    expect(armed(wire.sent.at(-1))).toBe(true)
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(armed(wire.sent.at(-1))).toBe(true)
  })

  it('ignores an arm pressed while Drive is not the active screen', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ, active: false }))
    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS * 5))
    expect(wire.sent.length).toBe(0)
  })

  it('keeps a standalone cockpit live as before', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ }))
    act(() => useVehicleStore.getState().arm())
    wire.sent = []
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.sent.length).toBe(2)
    expect(wire.sent.every(armed)).toBe(true)
  })
})

describe('an embedded cockpit', () => {
  let parentFrame: HTMLIFrameElement
  let parentWindow: Window

  beforeEach(() => {
    parentFrame = document.createElement('iframe')
    document.body.appendChild(parentFrame)
    parentWindow = parentFrame.contentWindow!
    Object.defineProperty(window, 'parent', { value: parentWindow, configurable: true })
    Object.defineProperty(document, 'referrer', { value: 'http://c2.test:5173/drive', configurable: true })
    forgetDriveActive()
  })

  afterEach(() => {
    Object.defineProperty(window, 'parent', { value: window, configurable: true })
    Object.defineProperty(document, 'referrer', { value: '', configurable: true })
    parentFrame.remove()
  })

  function fromParent(active: boolean, source: Window = parentWindow, origin = 'http://c2.test:5173') {
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', { data: { type: 'argus.drive.active', active }, source, origin }),
      )
    })
  }

  it('sends no command frames before the first active message', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ, active: useDriveActive() }))
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS * 10))
    expect(wire.sent.length).toBe(0)

    fromParent(true)
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.sent.length).toBe(2)
    // a fresh embed starts with the arm down
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('listens only to its parent window', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ, active: useDriveActive() }))
    const stranger = document.createElement('iframe')
    document.body.appendChild(stranger)
    fromParent(true, stranger.contentWindow!)
    act(() => vi.advanceTimersByTime(TICK_MS * 5))
    expect(wire.sent.length).toBe(0)
    stranger.remove()
  })

  it('listens only to the origin of the page that framed it', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ, active: useDriveActive() }))
    fromParent(true, parentWindow, 'http://evil.test')
    act(() => vi.advanceTimersByTime(TICK_MS * 5))
    expect(wire.sent.length).toBe(0)
    fromParent(true)
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.sent.length).toBe(2)
  })
})

describe('the arm bit on the wire', () => {
  it('never carries an arm pressed while Drive was hidden, until a fresh arm while active', () => {
    const { rerender } = renderHook(
      ({ active }) => useBridgeTransport('pw', true, { hz: HZ, active }),
      { initialProps: { active: false } },
    )
    // the gamepad keeps polling while Drive is hidden
    act(() => useVehicleStore.getState().arm())
    rerender({ active: true })
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS * 5))
    expect(wire.sent.length).toBe(5)
    expect(wire.sent.some(armed)).toBe(false)

    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.sent.slice(5).length).toBeGreaterThan(0)
    expect(wire.sent.slice(5).every(armed)).toBe(true)
  })

  it('still sends STOP while Drive is hidden', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ, active: false }))
    act(() => useVehicleStore.getState().estop())
    expect(wire.estops).toBe(1)
  })

  it('drops the arm when the link drops, and does not re-arm on reconnect', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ }))
    act(() => useVehicleStore.getState().arm())
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(armed(wire.sent.at(-1))).toBe(true)

    act(() => wire.status('closed'))
    expect(useVehicleStore.getState().command.safety.arm).toBe(false)
    // the local sim takes over the display and still reads DRIVING
    act(() => useVehicleStore.getState().tick(0.05))
    act(() => wire.status('connecting'))
    act(() => wire.status('open'))
    wire.sent = []
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS * 5))
    expect(wire.sent.length).toBe(5)
    expect(wire.sent.some(armed)).toBe(false)

    act(() => useVehicleStore.getState().arm())
    expect(armed(wire.sent.at(-1))).toBe(true)
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(armed(wire.sent.at(-1))).toBe(true)
  })

  it('ignores an arm pressed while the link is down', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ }))
    act(() => wire.status('closed'))
    act(() => useVehicleStore.getState().arm())
    act(() => wire.status('open'))
    wire.sent = []
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('keeps asserting the arm after the press even while telemetry lags', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ }))
    const st = () => useVehicleStore.getState()
    st().applyRemoteTelemetry({ ...st().telemetry, safetyState: 'STOPPED' })
    act(() => st().arm())
    // telemetry has not caught up: the daemon must not see arm=false
    act(() => vi.advanceTimersByTime(TICK_MS * 4))
    st().applyRemoteTelemetry({ ...st().telemetry, safetyState: 'STOPPED' })
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.sent.length).toBe(1 + 8)
    expect(wire.sent.every(armed)).toBe(true)

    // STOP ends it
    act(() => st().estop())
    wire.sent = []
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.sent.some(armed)).toBe(false)
  })

  it('stops asserting the arm when the vehicle reports it left DRIVING', () => {
    renderHook(() => useBridgeTransport('pw', true, { hz: HZ }))
    const st = () => useVehicleStore.getState()
    act(() => st().arm())
    driving()
    act(() => vi.advanceTimersByTime(TICK_MS))
    st().applyRemoteTelemetry({ ...st().telemetry, safetyState: 'LATCHED' })
    wire.sent = []
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.sent.some(armed)).toBe(false)
  })
})
