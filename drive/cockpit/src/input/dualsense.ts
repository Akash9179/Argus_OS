import type { Gear, Blinker } from '../contract'

/* DualSense → ARGUS command mapping (standard Gamepad mapping).
 * Continuous: left stick X → steer, R2 → throttle, L2 → brake.
 * Edges (rising): face buttons → gear, D-pad → blinker, Square → lights,
 * R1 → horn (or re-arm when L1 held), Options → E-STOP, Create → record. */

export const STICK_DEADZONE = 0.12

// standard-mapping button indices
const BTN = {
  cross: 0,
  circle: 1,
  square: 2,
  triangle: 3,
  l1: 4,
  r1: 5,
  l2: 6,
  r2: 7,
  create: 8,
  options: 9,
  dpadUp: 12,
  dpadDown: 13,
  dpadLeft: 14,
  dpadRight: 15,
} as const

export function applyDeadzone(v: number, dz = STICK_DEADZONE): number {
  const a = Math.abs(v)
  if (a < dz) return 0
  return Math.sign(v) * ((a - dz) / (1 - dz))
}

export interface GamepadReading {
  steer: number // -1..1
  throttle: number // 0..1 (R2 minus L2 brake, floored at 0)
  gear?: Gear
  blinker?: Blinker
  toggleLights: boolean
  toggleHorn: boolean
  toggleRecord: boolean
  arm: boolean
  estop: boolean
}

/** Pure reader: maps a Gamepad snapshot to a command reading.
 *  `prev` is the previous frame's `pressed` booleans (for rising-edge detection). */
export function readGamepad(gp: Gamepad, prev: boolean[]): GamepadReading {
  const b = gp.buttons
  const pressed = (i: number) => !!b[i]?.pressed
  const val = (i: number) => b[i]?.value ?? 0
  const rising = (i: number) => pressed(i) && !prev[i]

  const steer = applyDeadzone(gp.axes[0] ?? 0)
  const throttle = Math.max(0, Math.min(1, val(BTN.r2) - val(BTN.l2)))

  let gear: Gear | undefined
  if (rising(BTN.triangle)) gear = 'F'
  else if (rising(BTN.cross)) gear = 'N'
  else if (rising(BTN.circle)) gear = 'R'

  let blinker: Blinker | undefined
  if (rising(BTN.dpadLeft)) blinker = 'left'
  else if (rising(BTN.dpadRight)) blinker = 'right'
  else if (rising(BTN.dpadUp)) blinker = 'hazard'
  else if (rising(BTN.dpadDown)) blinker = 'off'

  // R1 honks; but L1+R1 is the deliberate two-button re-arm combo.
  const r1Rising = rising(BTN.r1)
  const arm = r1Rising && pressed(BTN.l1)
  const toggleHorn = r1Rising && !pressed(BTN.l1)

  return {
    steer,
    throttle,
    gear,
    blinker,
    toggleLights: rising(BTN.square),
    toggleHorn,
    toggleRecord: rising(BTN.create),
    arm,
    estop: rising(BTN.options),
  }
}

/** Current pressed snapshot, for storing as `prev` next frame. */
export function pressedSnapshot(gp: Gamepad): boolean[] {
  return gp.buttons.map((b) => !!b.pressed)
}
