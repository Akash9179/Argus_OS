import {
  clampSigned,
  clampUnit,
  type Command,
  type SafetyState,
  type Telemetry,
} from '../contract'

export const MAX_SPEED_KMH = 15
export const STEER_MAX_DEG = 30

const ACCEL_KMH_PER_S = 8
const DECEL_KMH_PER_S = 14

export interface SimState {
  speedKmh: number
  armed: boolean
  safetyState: SafetyState
  batteryPercent: number
  headingDeg: number
  prevArm: boolean
}

export function initialSimState(): SimState {
  return {
    speedKmh: 0,
    armed: true,
    safetyState: 'DRIVING',
    batteryPercent: 82,
    headingDeg: 47,
    prevArm: false,
  }
}

function approach(current: number, target: number, dtSec: number): number {
  const decelerating = Math.abs(target) < Math.abs(current)
  const rate = decelerating ? DECEL_KMH_PER_S : ACCEL_KMH_PER_S
  const maxDelta = rate * dtSec
  const diff = target - current
  if (Math.abs(diff) <= maxDelta) return target
  return current + Math.sign(diff) * maxDelta
}

export function stepVehicle(s: SimState, cmd: Command, dtSec: number): SimState {
  let armed = s.armed
  let safetyState = s.safetyState

  // E-STOP: highest priority.
  if (cmd.safety.estop) {
    safetyState = 'LATCHED'
    armed = false
  } else if (
    cmd.safety.arm &&
    !s.prevArm &&
    safetyState !== 'DRIVING'
  ) {
    // Re-arm on rising edge of arm.
    armed = true
    safetyState = 'DRIVING'
  }

  const driving = armed && safetyState === 'DRIVING'

  let target = 0
  if (driving) {
    const dir = cmd.gear === 'F' ? 1 : cmd.gear === 'R' ? -1 : 0
    target = dir * MAX_SPEED_KMH * clampUnit(cmd.throttle)
  }

  // When not driving, force decel toward 0.
  const speedKmh = driving
    ? approach(s.speedKmh, target, dtSec)
    : approach(s.speedKmh, 0, dtSec)

  // Battery drain.
  const drain =
    (0.0008 + Math.abs(speedKmh) * 0.00012) * dtSec * 100
  const batteryPercent = Math.max(0, s.batteryPercent - drain)

  // Heading integrates slowly from steer while moving.
  const headingDeg =
    (s.headingDeg + cmd.steer * Math.abs(speedKmh) * dtSec * 2 + 360) % 360

  return {
    speedKmh,
    armed,
    safetyState,
    batteryPercent,
    headingDeg,
    prevArm: cmd.safety.arm,
  }
}

export function toTelemetry(s: SimState, cmd: Command): Telemetry {
  return {
    speedKmh: Math.round(Math.abs(s.speedKmh) * 10) / 10,
    gear: cmd.gear,
    steerAngleDeg: Math.round(clampSigned(cmd.steer) * STEER_MAX_DEG),
    mode: cmd.mode,
    armed: s.armed,
    safetyState: s.safetyState,
    battery: {
      percent: Math.round(s.batteryPercent),
      runtimeMin: Math.round((s.batteryPercent / 100) * 50),
    },
    lights: {
      headlights: cmd.aux.headlights,
      blinker: cmd.aux.blinker,
      horn: cmd.aux.horn,
    },
    recording: cmd.aux.record,
    linkRttMs: 187,
    tempC: Math.round(48 + Math.abs(s.speedKmh) * 0.5),
    headingDeg: Math.round(s.headingDeg),
  }
}
