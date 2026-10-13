/**
 * The Remo link obeys the same rule as the bridge: leaving Drive
 * relinquishes control, and coming back needs a fresh arm.
 * The Remo transport is mocked. Nothing here opens a socket.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

interface Update {
  steer: number
  throttle: number
  gear: string
  driving: boolean
}

const wire = vi.hoisted(() => ({
  updates: [] as Update[],
  beats: 0,
  estops: 0,
  closes: 0,
  status: null as unknown as (s: string) => void,
}))

vi.mock('./remoTransport', () => ({
  RemoTransport: class {
    onStatus?: (s: string) => void
    connect() {
      wire.status = (s) => this.onStatus?.(s)
      this.onStatus?.('open')
    }
    update(i: Update) {
      wire.updates.push({ ...i })
    }
    heartbeat() {
      wire.beats++
    }
    estop() {
      wire.estops++
    }
    close() {
      wire.closes++
    }
  },
}))

import { useRemoTransport } from './useRemoTransport'
import { useVehicleStore } from '../state/store'
import { enterFrame, leaveFrame, parentSays, parentSignsOut } from '../embed/testFrame'

const HZ = 10
const TICK_MS = 1000 / HZ

beforeEach(() => {
  vi.useFakeTimers()
  wire.updates = []
  wire.beats = 0
  wire.estops = 0
  wire.closes = 0
  useVehicleStore.getState().reset()
  window.history.replaceState(null, '', '/?drive=localhost:8080')
})

afterEach(() => {
  vi.useRealTimers()
  window.history.replaceState(null, '', '/')
})

describe('leaving Drive on a Remo link', () => {
  beforeEach(() => {
    enterFrame()
    parentSays(true)
  })
  afterEach(leaveFrame)

  it('sends neutral at once, stops updates, and waits for a fresh arm on return', () => {
    renderHook(() => useRemoTransport('pw', true, { hz: HZ }))
    act(() => useVehicleStore.getState().arm())
    act(() => useVehicleStore.getState().setStick(0.4, 0.6))
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    // the operator armed, so the link is driving
    expect(wire.updates.at(-1)).toMatchObject({ driving: true, throttle: 0.6 })

    wire.updates = []
    act(() => parentSays(false))
    expect(wire.updates).toEqual([expect.objectContaining({ steer: 0, throttle: 0, driving: false })])
    act(() => vi.advanceTimersByTime(TICK_MS * 20))
    expect(wire.updates.length).toBe(1)
    expect(wire.beats).toBeGreaterThan(0)
    expect(wire.estops).toBe(0)

    act(() => parentSays(true))
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.updates.slice(1).every((u) => !u.driving)).toBe(true)

    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(wire.updates.at(-1)?.driving).toBe(true)
  })

  it('revokes in the same turn as the message, before any React render', () => {
    renderHook(() => useRemoTransport('pw', true, { hz: HZ }))
    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS))
    wire.updates = []

    // no act(): no effect or render may run between these lines
    parentSays(false)
    expect(wire.updates).toEqual([expect.objectContaining({ driving: false })])
    useVehicleStore.getState().arm()
    vi.advanceTimersByTime(TICK_MS * 3)
    expect(wire.updates.length).toBe(1)
    expect(useVehicleStore.getState().command.safety.arm).toBe(false)
  })

  it('sends neutral and closes the socket on sign-out, in the same turn', () => {
    renderHook(() => useRemoTransport('pw', true, { hz: HZ }))
    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS))
    wire.updates = []
    parentSignsOut()
    expect(wire.updates).toEqual([expect.objectContaining({ steer: 0, throttle: 0, driving: false })])
    expect(wire.closes).toBe(1)
    expect(useVehicleStore.getState().command.safety.arm).toBe(false)
    vi.advanceTimersByTime(TICK_MS * 3)
    expect(wire.updates.length).toBe(1)
  })

  it('still sends STOP while Drive is hidden', () => {
    act(() => parentSays(false))
    renderHook(() => useRemoTransport('pw', true, { hz: HZ }))
    act(() => useVehicleStore.getState().estop())
    expect(wire.estops).toBe(1)
    expect(wire.updates.some((u) => u.driving)).toBe(false)
  })
})

describe('the Remo link', () => {
  it('does not drive on the local sim reading alone', () => {
    renderHook(() => useRemoTransport('pw', true, { hz: HZ }))
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.updates.some((u) => u.driving)).toBe(false)
  })

  it('drops the arm when the link drops, and waits for a fresh arm on reconnect', () => {
    renderHook(() => useRemoTransport('pw', true, { hz: HZ }))
    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.updates.at(-1)?.driving).toBe(true)

    act(() => wire.status('closed'))
    expect(useVehicleStore.getState().command.safety.arm).toBe(false)
    act(() => wire.status('connecting'))
    act(() => wire.status('open'))
    wire.updates = []
    act(() => vi.advanceTimersByTime(TICK_MS * 3))
    expect(wire.updates.some((u) => u.driving)).toBe(false)

    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(wire.updates.at(-1)?.driving).toBe(true)
  })
})
