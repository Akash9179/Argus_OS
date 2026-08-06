import { describe, it, expect } from 'vitest'
import { intentToCommand, clampDurationMs, DRIVE_CAPS } from './driveIntent'
import { TokenEmitter, throttleToP, MAX_P } from '../transport/tokens'

describe('intentToCommand', () => {
  it('forward drives at the throttle cap in forward gear', () => {
    const c = intentToCommand({ action: 'forward' })
    expect(c.gear).toBe('F')
    expect(c.throttle).toBe(DRIVE_CAPS.throttleCap)
    expect(c.throttle).toBeLessThanOrEqual(DRIVE_CAPS.throttleCap)
    expect(c.steer).toBe(0)
  })

  it('left/right steer full', () => {
    expect(intentToCommand({ action: 'left' }).steer).toBe(-1)
    expect(intentToCommand({ action: 'right' }).steer).toBe(1)
  })

  it('stop and none return a neutral, non-driving command', () => {
    for (const action of ['stop', 'none'] as const) {
      const c = intentToCommand({ action })
      expect(c.throttle).toBe(0)
      expect(c.steer).toBe(0)
    }
  })

  it('never exceeds the throttle cap even if a lower cap is given', () => {
    const c = intentToCommand({ action: 'forward' }, { throttleCap: 0.25, maxDriveMs: 1000 })
    expect(c.throttle).toBe(0.25)
  })
})

describe('intent → real Remo tokens (bounded burst)', () => {
  it('forward intent emits a single P-token at the cap, below hardware max', () => {
    const cmd = intentToCommand({ action: 'forward' })
    const em = new TokenEmitter()
    const tokens = em.update({ steer: cmd.steer, throttle: cmd.throttle, gear: cmd.gear, driving: true })
    const pTok = tokens.find((t) => t.startsWith('P'))!
    const p = Number(pTok.slice(1))
    expect(p).toBe(throttleToP(DRIVE_CAPS.throttleCap))
    expect(p).toBeLessThan(MAX_P) // strictly below the forward-only hardware maximum
  })

  it('auto-neutral emits P42 + L0 + R0', () => {
    const em = new TokenEmitter()
    expect(em.forceNeutral()).toEqual(['P42', 'L0', 'R0'])
  })
})

describe('clampDurationMs', () => {
  it('clamps to the cap and defaults when unset', () => {
    expect(clampDurationMs(5000)).toBe(DRIVE_CAPS.maxDriveMs)
    expect(clampDurationMs(undefined)).toBeLessThanOrEqual(DRIVE_CAPS.maxDriveMs)
    expect(clampDurationMs(300)).toBe(300)
    expect(clampDurationMs(-100)).toBe(0)
  })
})
