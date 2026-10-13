/**
 * Held input must let go when the operator's attention leaves the cockpit.
 * Keys release when focus leaves the frame or the tab hides. A gamepad that
 * disconnects leaves no stick command behind.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useManualDrive } from './useManualDrive'
import { useGamepad } from './useGamepad'
import { useVehicleStore } from '../state/store'

function key(type: 'keydown' | 'keyup', k: string) {
  window.dispatchEvent(new KeyboardEvent(type, { key: k }))
}

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

beforeEach(() => useVehicleStore.getState().reset())

describe('held keys', () => {
  afterEach(() => setVisibility('visible'))

  it('release when focus leaves the frame', () => {
    renderHook(() => useManualDrive(true))
    act(() => key('keydown', 'ArrowUp'))
    expect(useVehicleStore.getState().command.throttle).toBeGreaterThan(0)
    act(() => {
      window.dispatchEvent(new Event('blur'))
    })
    expect(useVehicleStore.getState().command.throttle).toBe(0)
  })

  it('release when the tab hides', () => {
    renderHook(() => useManualDrive(true))
    act(() => key('keydown', 'ArrowUp'))
    act(() => key('keydown', 'ArrowLeft'))
    expect(useVehicleStore.getState().command.throttle).toBeGreaterThan(0)
    act(() => setVisibility('hidden'))
    expect(useVehicleStore.getState().command.throttle).toBe(0)
    expect(useVehicleStore.getState().command.steer).toBe(0)
  })
})

describe('a gamepad that disconnects', () => {
  let pads: (Gamepad | null)[] = []
  let frames: FrameRequestCallback[] = []

  function frame() {
    const run = frames
    frames = []
    act(() => run.forEach((cb) => cb(0)))
  }

  beforeEach(() => {
    frames = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frames.push(cb)
      return frames.length
    })
    vi.stubGlobal('cancelAnimationFrame', () => {})
    Object.defineProperty(navigator, 'getGamepads', { value: () => pads, configurable: true })
  })

  afterEach(() => vi.unstubAllGlobals())

  it('leaves the stick neutral', () => {
    const axes = [0.8, 0, 0, 0]
    const buttons = Array.from({ length: 17 }, (_, i) => ({
      pressed: i === 7,
      touched: i === 7,
      value: i === 7 ? 1 : 0,
    }))
    pads = [{ id: 'pad', axes, buttons, connected: true, mapping: 'standard', index: 0 } as unknown as Gamepad]
    renderHook(() => useGamepad())
    frame()
    const held = useVehicleStore.getState().command
    expect(held.steer).not.toBe(0)
    expect(held.throttle).toBeGreaterThan(0)

    pads = []
    frame()
    const after = useVehicleStore.getState().command
    expect(after.steer).toBe(0)
    expect(after.throttle).toBe(0)
  })

  it('arms only through the same gate as the ARM button', () => {
    const st = useVehicleStore.getState()
    // a vehicle link whose self-test failed
    st.setLinked(true)
    st.setRemote(true)
    st.applyPreflight({ ran: true, pass: false, checks: [{ name: 'mcu', ok: false, detail: '' }] })
    st.applyRemoteTelemetry({ ...st.telemetry, ignition: true, safetyState: 'STOPPED' })
    const pad = (pressed: number[]) =>
      ({
        id: 'pad',
        axes: [0, 0, 0, 0],
        buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: pressed.includes(i), touched: false, value: pressed.includes(i) ? 1 : 0 })),
        connected: true,
        mapping: 'standard',
        index: 0,
      }) as unknown as Gamepad
    pads = [pad([4])]
    renderHook(() => useGamepad())
    frame()
    // L1 held, R1 pressed: the two-button arm combo
    pads = [pad([4, 5])]
    frame()
    expect(useVehicleStore.getState().command.safety.arm).toBe(false)
    expect(useVehicleStore.getState().armPresses).toBe(0)
  })
})
