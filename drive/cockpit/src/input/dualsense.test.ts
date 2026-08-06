import { describe, it, expect } from 'vitest'
import { readGamepad, applyDeadzone, pressedSnapshot } from './dualsense'

/** Build a fake standard-mapping Gamepad. */
function pad(opts: { axes?: number[]; pressed?: number[]; values?: Record<number, number> } = {}): Gamepad {
  const axes = opts.axes ?? [0, 0, 0, 0]
  const pressedIdx = new Set(opts.pressed ?? [])
  const buttons = Array.from({ length: 18 }, (_, i) => ({
    pressed: pressedIdx.has(i),
    touched: false,
    value: opts.values?.[i] ?? (pressedIdx.has(i) ? 1 : 0),
  }))
  return { axes, buttons, connected: true, id: 'DualSense', index: 0, mapping: 'standard', timestamp: 0 } as unknown as Gamepad
}

const NONE: boolean[] = new Array(18).fill(false)

describe('applyDeadzone', () => {
  it('zeroes small noise and rescales', () => {
    expect(applyDeadzone(0.05)).toBe(0)
    expect(applyDeadzone(1)).toBeCloseTo(1, 5)
    expect(applyDeadzone(-1)).toBeCloseTo(-1, 5)
  })
})

describe('readGamepad', () => {
  it('maps left stick X to steer past the deadzone', () => {
    const r = readGamepad(pad({ axes: [0.9, 0, 0, 0] }), NONE)
    expect(r.steer).toBeGreaterThan(0.5)
  })

  it('maps R2 to throttle and L2 brake subtracts', () => {
    expect(readGamepad(pad({ values: { 7: 1 } }), NONE).throttle).toBe(1)
    expect(readGamepad(pad({ values: { 7: 0.8, 6: 0.5 } }), NONE).throttle).toBeCloseTo(0.3, 5)
    expect(readGamepad(pad({ values: { 7: 0.2, 6: 1 } }), NONE).throttle).toBe(0)
  })

  it('detects gear on rising edge of face buttons', () => {
    expect(readGamepad(pad({ pressed: [3] }), NONE).gear).toBe('F') // triangle
    expect(readGamepad(pad({ pressed: [1] }), NONE).gear).toBe('R') // circle
    expect(readGamepad(pad({ pressed: [0] }), NONE).gear).toBe('N') // cross
  })

  it('does not re-fire gear while the button stays held', () => {
    const held = new Array(18).fill(false)
    held[3] = true
    expect(readGamepad(pad({ pressed: [3] }), held).gear).toBeUndefined()
  })

  it('maps D-pad to blinker states', () => {
    expect(readGamepad(pad({ pressed: [14] }), NONE).blinker).toBe('left')
    expect(readGamepad(pad({ pressed: [15] }), NONE).blinker).toBe('right')
    expect(readGamepad(pad({ pressed: [12] }), NONE).blinker).toBe('hazard')
  })

  it('R1 honks, but L1+R1 re-arms instead', () => {
    const horn = readGamepad(pad({ pressed: [5] }), NONE)
    expect(horn.toggleHorn).toBe(true)
    expect(horn.arm).toBe(false)

    const rearm = readGamepad(pad({ pressed: [4, 5] }), NONE) // L1 held + R1
    expect(rearm.arm).toBe(true)
    expect(rearm.toggleHorn).toBe(false)
  })

  it('Options is E-STOP, Create is record, Square is lights', () => {
    expect(readGamepad(pad({ pressed: [9] }), NONE).estop).toBe(true)
    expect(readGamepad(pad({ pressed: [8] }), NONE).toggleRecord).toBe(true)
    expect(readGamepad(pad({ pressed: [2] }), NONE).toggleLights).toBe(true)
  })

  it('pressedSnapshot reflects pressed buttons', () => {
    const snap = pressedSnapshot(pad({ pressed: [3, 5] }))
    expect(snap[3]).toBe(true)
    expect(snap[5]).toBe(true)
    expect(snap[0]).toBe(false)
  })
})
