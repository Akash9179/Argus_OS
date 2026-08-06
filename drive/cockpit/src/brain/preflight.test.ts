import { describe, it, expect } from 'vitest'
import { evaluatePreflight } from './preflight'
import type { Telemetry } from '../contract'

const base: Telemetry = {
  ignition: true,
  speedKmh: 0, gear: 'N', steerAngleDeg: 0, mode: 'MANUAL', armed: false,
  safetyState: 'STOPPED', battery: { percent: 90, runtimeMin: 120 },
  lights: { headlights: false, blinker: 'off', horn: false }, recording: true,
  linkRttMs: 80, tempC: 40, headingDeg: 0,
}

describe('evaluatePreflight', () => {
  it('reports all ok for a healthy vehicle', () => {
    const results = evaluatePreflight(base)
    expect(results.every((r) => r.status === 'ok')).toBe(true)
    expect(results.map((r) => r.item)).toEqual(
      expect.arrayContaining(['Battery', 'Link', 'Temperature', 'Armed', 'Safety', 'Gear']),
    )
  })

  it('flags low battery as fail and marginal battery as warn', () => {
    expect(evaluatePreflight({ ...base, battery: { percent: 15, runtimeMin: 5 } }).find((r) => r.item === 'Battery')!.status).toBe('fail')
    expect(evaluatePreflight({ ...base, battery: { percent: 30, runtimeMin: 20 } }).find((r) => r.item === 'Battery')!.status).toBe('warn')
  })

  it('flags a stale link as fail', () => {
    expect(evaluatePreflight({ ...base, linkRttMs: 800 }).find((r) => r.item === 'Link')!.status).toBe('fail')
  })

  it('flags high temperature as fail', () => {
    expect(evaluatePreflight({ ...base, tempC: 80 }).find((r) => r.item === 'Temperature')!.status).toBe('fail')
  })

  it('flags a LATCHED safety state as fail', () => {
    expect(evaluatePreflight({ ...base, safetyState: 'LATCHED' }).find((r) => r.item === 'Safety')!.status).toBe('fail')
  })
})
