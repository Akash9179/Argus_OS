import { describe, it, expect } from 'vitest'
import {
  TokenEmitter,
  throttleToP,
  NEUTRAL_P,
  MAX_P,
  type DriveInput,
} from './tokens'

const F = (o: Partial<DriveInput> = {}): DriveInput => ({
  steer: 0,
  throttle: 0,
  gear: 'F',
  driving: true,
  ...o,
})

describe('throttleToP', () => {
  it('maps 0 -> neutral, 1 -> max', () => {
    expect(throttleToP(0)).toBe(NEUTRAL_P)
    expect(throttleToP(1)).toBe(MAX_P)
  })
  it('midpoint ~ halfway', () => {
    expect(throttleToP(0.5)).toBe(128) // round(42 + 86)
  })
  it('clamps out-of-range', () => {
    expect(throttleToP(-3)).toBe(NEUTRAL_P)
    expect(throttleToP(9)).toBe(MAX_P)
  })
})

describe('TokenEmitter throttle', () => {
  it('emits P only on change', () => {
    const e = new TokenEmitter()
    expect(e.update(F({ throttle: 0 }))).toEqual([]) // already neutral
    expect(e.update(F({ throttle: 0.5 }))).toEqual(['P128'])
    expect(e.update(F({ throttle: 0.5 }))).toEqual([]) // unchanged
    expect(e.update(F({ throttle: 0 }))).toEqual(['P42'])
  })
  it('forces neutral when not driving', () => {
    const e = new TokenEmitter()
    e.update(F({ throttle: 0.8 })) // P179
    expect(e.update(F({ throttle: 0.8, driving: false }))).toEqual(['P42'])
  })
  it('forces neutral in non-forward gear (no reverse on hardware)', () => {
    const e = new TokenEmitter()
    e.update(F({ throttle: 0.8 }))
    expect(e.update(F({ throttle: 0.8, gear: 'R' }))).toEqual(['P42'])
  })
})

describe('TokenEmitter steering', () => {
  it('engages and releases with deadband', () => {
    const e = new TokenEmitter()
    expect(e.update(F({ steer: 0.05 }))).toEqual([]) // inside deadband
    expect(e.update(F({ steer: 0.5 }))).toEqual(['R1'])
    expect(e.update(F({ steer: 0.5 }))).toEqual([]) // held
    expect(e.update(F({ steer: 0 }))).toEqual(['R0'])
  })
  it('switches sides cleanly (release old, engage new)', () => {
    const e = new TokenEmitter()
    e.update(F({ steer: 0.5 })) // R1
    expect(e.update(F({ steer: -0.5 }))).toEqual(['R0', 'L1'])
  })
  it('centers steering when not driving', () => {
    const e = new TokenEmitter()
    e.update(F({ steer: -0.9 })) // L1
    expect(e.update(F({ steer: -0.9, driving: false }))).toEqual(['L0'])
  })
})

describe('forceNeutral', () => {
  it('always returns full neutral and resets state', () => {
    const e = new TokenEmitter()
    e.update(F({ steer: 0.9, throttle: 0.9 }))
    expect(e.forceNeutral()).toEqual(['P42', 'L0', 'R0'])
    // after reset, a fresh neutral input emits nothing
    expect(e.update(F())).toEqual([])
  })
})
