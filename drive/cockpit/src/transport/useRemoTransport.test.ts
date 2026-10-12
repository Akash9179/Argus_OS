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

const wire = vi.hoisted(() => ({ updates: [] as Update[], beats: 0, estops: 0 }))

vi.mock('./remoTransport', () => ({
  RemoTransport: class {
    onStatus?: (s: string) => void
    connect() {
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
    close() {}
  },
}))

import { useRemoTransport } from './useRemoTransport'
import { useVehicleStore } from '../state/store'

const HZ = 10
const TICK_MS = 1000 / HZ

beforeEach(() => {
  vi.useFakeTimers()
  wire.updates = []
  wire.beats = 0
  wire.estops = 0
  useVehicleStore.getState().reset()
  window.history.replaceState(null, '', '/?drive=localhost:8080')
})

afterEach(() => {
  vi.useRealTimers()
  window.history.replaceState(null, '', '/')
})

describe('leaving Drive on a Remo link', () => {
  it('sends neutral at once, stops updates, and waits for a fresh arm on return', () => {
    const { rerender } = renderHook(
      ({ active }) => useRemoTransport('pw', true, { hz: HZ, active }),
      { initialProps: { active: true } },
    )
    act(() => useVehicleStore.getState().setStick(0.4, 0.6))
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    // the local sim starts armed, so the link is driving
    expect(wire.updates.at(-1)).toMatchObject({ driving: true, throttle: 0.6 })

    wire.updates = []
    rerender({ active: false })
    expect(wire.updates).toEqual([expect.objectContaining({ steer: 0, throttle: 0, driving: false })])
    act(() => vi.advanceTimersByTime(TICK_MS * 20))
    expect(wire.updates.length).toBe(1)
    expect(wire.beats).toBeGreaterThan(0)
    expect(wire.estops).toBe(0)

    rerender({ active: true })
    act(() => vi.advanceTimersByTime(TICK_MS * 2))
    expect(wire.updates.slice(1).every((u) => !u.driving)).toBe(true)

    act(() => useVehicleStore.getState().arm())
    act(() => vi.advanceTimersByTime(TICK_MS))
    expect(wire.updates.at(-1)?.driving).toBe(true)
  })
})
