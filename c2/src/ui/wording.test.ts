/**
 * The words, tested. Most of these encode a law rather than a preference:
 * confidence never rounds up, unknown vocabulary never renders as healthy,
 * and a time is never ambiguous about which day it means.
 */
import { describe, expect, it } from 'vitest'
import {
  agoInWords,
  assetStatus,
  clockAt,
  outOfTen,
  say,
  severityStatus,
  statusInWords,
} from './wording'

describe('outOfTen', () => {
  it('never rounds up and never reaches ten', () => {
    // The world model caps confidence at 0.99 so the system never claims
    // certainty. Rounding here would undo that on the last step.
    expect(outOfTen(0.99)).toBe(9)
    expect(outOfTen(0.49)).toBe(4)
    expect(outOfTen(0.05)).toBe(0)
    // The clamp, not just the floor: even a server that claimed certainty
    // outright would render as 9 in 10, never 10.
    expect(outOfTen(1)).toBe(9)
  })

  it('says nothing rather than zero when there is no figure', () => {
    expect(outOfTen(undefined)).toBeNull()
    expect(outOfTen(Number.NaN)).toBeNull()
  })
})

describe('clockAt', () => {
  it('always carries the Z', () => {
    expect(clockAt(Date.now() / 1000)).toMatch(/^\d\d:\d\d Z$/)
  })

  it('carries its date when it is not from today', () => {
    // A machine that went quiet last night must not read as this
    // afternoon. This is the client half of the same rule the server
    // applies to order times.
    const lastYear = Date.UTC(2025, 7, 2, 23, 58) / 1000
    expect(clockAt(lastYear)).toBe('23:58 Z on 02 August')
  })
})

describe('unknown vocabulary', () => {
  it('a status word from a newer machine reads as attention, not health', () => {
    expect(assetStatus('ASSET_STATUS_SOMETHING_NEW', true)).toBe('warn')
    expect(statusInWords('ASSET_STATUS_LIMPING', true)).toBe('Limping')
  })

  it('an unknown event severity is never green', () => {
    expect(severityStatus('catastrophic')).toBe('warn')
  })

  it('a machine that is not answering reads off, whatever it last said', () => {
    expect(assetStatus('ASSET_STATUS_ACTIVE', false)).toBe('off')
  })
})

describe('the compass', () => {
  it('gives the eight points and wraps correctly', () => {
    expect(say.machine.heading(0)).toBe('N')
    expect(say.machine.heading(45)).toBe('NE')
    expect(say.machine.heading(180)).toBe('S')
    expect(say.machine.heading(350)).toBe('N')
    expect(say.machine.heading(-90)).toBe('W')
  })
})

describe('agoInWords', () => {
  it('rounds seconds to five so the number does not fake precision', () => {
    expect(agoInWords(4)).toBe('a few seconds ago')
    expect(agoInWords(47)).toBe('45 seconds ago')
    expect(agoInWords(3000)).toBe('50 minutes ago')
  })
})
