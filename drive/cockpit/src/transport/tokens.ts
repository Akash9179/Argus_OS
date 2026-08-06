import type { Gear } from '../contract'

/**
 * Pure mapping from the ARGUS Command contract to the Remo serial token protocol
 * (reverse-engineered — see ARGUS_INTEGRATION_NOTES.md at the repo root):
 *   throttle : P<n>, n in [42,214], neutral/stop = P42  (forward-only)
 *   steering : L1/L0/R1/R0  (bang-bang, hold-to-steer)
 *
 * This module is deliberately framework-free and side-effect-free so it can be
 * unit-tested in isolation. The WebSocket plumbing lives in remoTransport.ts.
 */

export const NEUTRAL_P = 42
export const MAX_P = 214
export const STEER_DEADBAND = 0.12

/** throttle 0..1 -> P token value, clamped. P = round(42 + 172*throttle). */
export function throttleToP(throttle: number): number {
  const t = Math.max(0, Math.min(1, throttle))
  return Math.round(NEUTRAL_P + t * (MAX_P - NEUTRAL_P))
}

export interface DriveInput {
  steer: number // -1..1
  throttle: number // 0..1
  gear: Gear
  /** true only when the vehicle is armed & DRIVING; false latches output to neutral */
  driving: boolean
}

type SteerState = -1 | 0 | 1

/**
 * Stateful, diff-based emitter: call update() each tick and it returns ONLY the
 * tokens that changed since last time (matching how the Remo web UI sends on
 * change, not as a stream). Hardware is forward-only, so reverse/neutral gear
 * and any non-DRIVING safety state collapse throttle to P42.
 */
export class TokenEmitter {
  private lastP = NEUTRAL_P
  private steerState: SteerState = 0

  update(i: DriveInput): string[] {
    const out: string[] = []
    const live = i.driving

    // throttle — only forward gear, only while driving
    const throttle = live && i.gear === 'F' ? i.throttle : 0
    const p = throttleToP(throttle)
    if (p !== this.lastP) {
      out.push('P' + p)
      this.lastP = p
    }

    // steering — bang-bang with deadband; centered when not driving
    const s = live ? i.steer : 0
    const want: SteerState = s > STEER_DEADBAND ? 1 : s < -STEER_DEADBAND ? -1 : 0
    if (want !== this.steerState) {
      if (this.steerState === 1) out.push('R0')
      if (this.steerState === -1) out.push('L0')
      if (want === 1) out.push('R1')
      if (want === -1) out.push('L1')
      this.steerState = want
    }
    return out
  }

  /** Unconditional full neutral — for E-STOP, disconnect, page unload. */
  forceNeutral(): string[] {
    this.lastP = NEUTRAL_P
    this.steerState = 0
    return ['P' + NEUTRAL_P, 'L0', 'R0']
  }
}
