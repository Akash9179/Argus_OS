import { neutralCommand, type Command } from '../contract'
import type { DriveIntent } from './types'

export interface DriveCaps {
  throttleCap: number
  maxDriveMs: number
}

/** Hard bounds on any brain-issued drive action. */
export const DRIVE_CAPS: DriveCaps = { throttleCap: 0.35, maxDriveMs: 1200 }

export function clampDurationMs(requested: number | undefined, caps: DriveCaps = DRIVE_CAPS): number {
  const want = requested ?? 600
  return Math.max(0, Math.min(caps.maxDriveMs, want))
}

export function intentToCommand(intent: DriveIntent, caps: DriveCaps = DRIVE_CAPS): Command {
  const cmd = neutralCommand()
  switch (intent.action) {
    case 'forward':
      cmd.gear = 'F'
      cmd.throttle = caps.throttleCap
      break
    case 'left':
      cmd.steer = -1
      break
    case 'right':
      cmd.steer = 1
      break
    case 'stop':
    case 'none':
      break
  }
  return cmd
}
