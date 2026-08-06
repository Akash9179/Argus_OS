import { describe, it, expect } from 'vitest'
import { neutralCommand, type Command } from '../contract'
import {
  MAX_SPEED_KMH,
  STEER_MAX_DEG,
  initialSimState,
  stepVehicle,
  toTelemetry,
} from './dummyVehicle'

function cmd(overrides: Partial<Command> = {}): Command {
  const base = neutralCommand()
  return { ...base, ...overrides }
}

function runSteps(
  state: ReturnType<typeof initialSimState>,
  command: Command,
  steps: number,
  dt = 0.05,
) {
  let s = state
  for (let i = 0; i < steps; i++) s = stepVehicle(s, command, dt)
  return s
}

describe('initialSimState', () => {
  it('starts armed, DRIVING, speed 0', () => {
    const s = initialSimState()
    expect(s.speedKmh).toBe(0)
    expect(s.armed).toBe(true)
    expect(s.safetyState).toBe('DRIVING')
  })
})

describe('stepVehicle speed', () => {
  it('throttle in F integrates speed up and caps at MAX_SPEED_KMH', () => {
    const c = cmd({ gear: 'F', throttle: 1 })
    const afterShort = runSteps(initialSimState(), c, 2)
    expect(afterShort.speedKmh).toBeGreaterThan(0)
    expect(afterShort.speedKmh).toBeLessThan(MAX_SPEED_KMH)

    const afterLong = runSteps(initialSimState(), c, 400)
    expect(afterLong.speedKmh).toBeLessThanOrEqual(MAX_SPEED_KMH + 1e-6)
    expect(afterLong.speedKmh).toBeGreaterThan(MAX_SPEED_KMH - 0.01)
  })

  it('releasing throttle decays speed to 0', () => {
    const moving = runSteps(initialSimState(), cmd({ gear: 'F', throttle: 1 }), 400)
    expect(moving.speedKmh).toBeGreaterThan(0)
    const stopped = runSteps(moving, cmd({ gear: 'F', throttle: 0 }), 400)
    expect(stopped.speedKmh).toBeCloseTo(0, 5)
  })

  it('gear R gives negative speedKmh', () => {
    const s = runSteps(initialSimState(), cmd({ gear: 'R', throttle: 1 }), 10)
    expect(s.speedKmh).toBeLessThan(0)
  })
})

describe('stepVehicle safety', () => {
  it('estop latches and zeroes speed and stays zero under throttle', () => {
    let s = runSteps(initialSimState(), cmd({ gear: 'F', throttle: 1 }), 50)
    expect(s.speedKmh).toBeGreaterThan(0)

    s = stepVehicle(s, cmd({ gear: 'F', throttle: 1, safety: { arm: false, estop: true } }), 0.05)
    expect(s.safetyState).toBe('LATCHED')
    expect(s.armed).toBe(false)

    s = runSteps(s, cmd({ gear: 'F', throttle: 1 }), 400)
    expect(s.speedKmh).toBeCloseTo(0, 5)
  })

  it('re-arm rising edge from LATCHED returns to DRIVING', () => {
    let s = stepVehicle(
      initialSimState(),
      cmd({ safety: { arm: false, estop: true } }),
      0.05,
    )
    expect(s.safetyState).toBe('LATCHED')

    // rising edge of arm
    s = stepVehicle(s, cmd({ safety: { arm: true, estop: false } }), 0.05)
    expect(s.safetyState).toBe('DRIVING')
    expect(s.armed).toBe(true)
  })
})

describe('battery', () => {
  it('strictly decreases while driving', () => {
    const c = cmd({ gear: 'F', throttle: 1 })
    let s = initialSimState()
    const start = s.batteryPercent
    s = runSteps(s, c, 200)
    expect(s.batteryPercent).toBeLessThan(start)
    expect(s.batteryPercent).toBeGreaterThanOrEqual(0)
  })
})

describe('toTelemetry', () => {
  it('echoes headlights and recording from cmd and steerAngle from steer', () => {
    const c = cmd({
      steer: 1,
      aux: { headlights: true, blinker: 'left', horn: false, record: true },
    })
    const t = toTelemetry(initialSimState(), c)
    expect(t.lights.headlights).toBe(true)
    expect(t.lights.blinker).toBe('left')
    expect(t.recording).toBe(true)
    expect(t.steerAngleDeg).toBe(STEER_MAX_DEG)
  })

  it('reports non-negative speed', () => {
    const s = runSteps(initialSimState(), cmd({ gear: 'R', throttle: 1 }), 10)
    const t = toTelemetry(s, cmd({ gear: 'R', throttle: 1 }))
    expect(t.speedKmh).toBeGreaterThanOrEqual(0)
  })
})
