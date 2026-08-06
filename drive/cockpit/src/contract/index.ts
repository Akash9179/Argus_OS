export type Gear = 'R' | 'N' | 'F'
export type DriveMode = 'MANUAL' | 'AUTO'
export type SafetyState = 'DRIVING' | 'STOPPED' | 'LATCHED'
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
}

export interface PreflightState {
  ran: boolean
  pass: boolean
  checks: PreflightCheck[]
}

export const noPreflight = (): PreflightState => ({ ran: false, pass: false, checks: [] })
