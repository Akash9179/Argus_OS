export type Gear = 'R' | 'N' | 'F'
export type DriveMode = 'MANUAL' | 'AUTO'
/**
 * The vehicle's safety state. Telemetry is parsed from JSON unchecked, so a
 * newer daemon may send a value this cockpit does not know. It passes
 * through as itself and is shown as not understood, never dropped or
 * mapped onto a known state.
 */
export type SafetyState = 'DRIVING' | 'STOPPED' | 'LATCHED' | (string & {})
export type Blinker = 'off' | 'left' | 'right' | 'hazard'

export interface Command {
  steer: number // -1..1
  throttle: number // 0..1
  gear: Gear
  mode: DriveMode
  aux: { ignition: boolean; headlights: boolean; blinker: Blinker; horn: boolean; record: boolean }
  safety: { arm: boolean; estop: boolean }
}

export interface Telemetry {
  ignition: boolean
  speedKmh: number
  gear: Gear
  steerAngleDeg: number
  mode: DriveMode
  armed: boolean
  safetyState: SafetyState
  battery: { percent: number; runtimeMin: number }
  lights: { headlights: boolean; blinker: Blinker; horn: boolean }
  recording: boolean
  linkRttMs: number
  tempC: number
  headingDeg: number
}

export const clampUnit = (n: number) => Math.max(0, Math.min(1, n))
export const clampSigned = (n: number) => Math.max(-1, Math.min(1, n))

export function neutralCommand(): Command {
  return {
    steer: 0,
    throttle: 0,
    gear: 'F',
    mode: 'MANUAL',
    aux: { ignition: false, headlights: false, blinker: 'off', horn: false, record: true },
    safety: { arm: false, estop: false },
  }
}

export interface PreflightCheck {
  name: string
  ok: boolean
  detail: string
  /** The check as a sentence, from the daemon. Absent from an older daemon. */
  label?: string
}

/**
 * What the daemon tells a cockpit when it grants a role: who is driving (as
 * the operator file spells it), what the machine is called (null when it
 * has no declared name), and the watchdog window, so the cockpit can state
 * what happens on link loss with the daemon's own figure.
 */
export interface SessionFacts {
  role: 'DRIVER' | 'SPECTATOR'
  driver: string
  vehicle: string | null
  watchdogMs: number | null
  /** When this cockpit was granted its role, ms since the epoch. */
  since: number
}

export interface PreflightState {
  ran: boolean
  pass: boolean
  checks: PreflightCheck[]
}

export const noPreflight = (): PreflightState => ({ ran: false, pass: false, checks: [] })
