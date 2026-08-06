// Pure decision for one tick of the brain-assist assert-loop. Kept separate
// from the React component so the safety-critical behavior (human override +
// auto-neutral) is deterministically unit-testable.

export interface AssistState {
  steer: number
  throttle: number
  /** timestamp (ms, monotonic) after which the nudge auto-neutralizes */
  until: number
}

export type AssistStep =
  | { kind: 'assert'; steer: number; throttle: number } // keep driving within the window
  | { kind: 'neutralize' } // window elapsed → set neutral once, then clear
  | { kind: 'yield' } // live command diverged (human took over) → clear, don't touch
  | { kind: 'idle' } // no active assist

export function assistStep(
  a: AssistState | null,
  cur: { steer: number; throttle: number },
  now: number,
): AssistStep {
  if (!a) return { kind: 'idle' }
  // HUMAN OVERRIDE: anything other than assist wrote the command since last tick.
  if (cur.steer !== a.steer || cur.throttle !== a.throttle) return { kind: 'yield' }
  if (now >= a.until) return { kind: 'neutralize' }
  return { kind: 'assert', steer: a.steer, throttle: a.throttle }
}
