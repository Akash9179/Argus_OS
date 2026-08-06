import { describe, it, expect } from 'vitest'
import { assistStep, type AssistState } from './assistLoop'

const active: AssistState = { steer: 0, throttle: 0.35, until: 1000 }

describe('assistStep', () => {
  it('idles when there is no active assist', () => {
    expect(assistStep(null, { steer: 0, throttle: 0 }, 0)).toEqual({ kind: 'idle' })
  })

  it('asserts the command while within the window and uncontested', () => {
    expect(assistStep(active, { steer: 0, throttle: 0.35 }, 500)).toEqual({
      kind: 'assert',
      steer: 0,
      throttle: 0.35,
    })
  })

  it('YIELDS to a human the instant the live command diverges (throttle)', () => {
    expect(assistStep(active, { steer: 0, throttle: 0.5 }, 500)).toEqual({ kind: 'yield' })
  })

  it('YIELDS to a human the instant the live command diverges (steer)', () => {
    expect(assistStep(active, { steer: -1, throttle: 0.35 }, 500)).toEqual({ kind: 'yield' })
  })

  it('AUTO-NEUTRALIZES once the window elapses', () => {
    expect(assistStep(active, { steer: 0, throttle: 0.35 }, 1000)).toEqual({ kind: 'neutralize' })
    expect(assistStep(active, { steer: 0, throttle: 0.35 }, 1500)).toEqual({ kind: 'neutralize' })
  })

  it('override takes precedence over expiry when both could apply', () => {
    // diverged AND past deadline → yield (don't stomp the human with a neutral)
    expect(assistStep(active, { steer: 0, throttle: 0.5 }, 2000)).toEqual({ kind: 'yield' })
  })
})
