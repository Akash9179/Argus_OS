import type { Telemetry } from '../contract'

export type DriveAction = 'forward' | 'left' | 'right' | 'stop' | 'none'

export interface DriveIntent {
  action: DriveAction
  durationMs?: number
}

export interface CheckResult {
  item: string
  status: 'ok' | 'warn' | 'fail'
  detail: string
}

export interface BrainTurn {
  transcript: string
  cameraFrameJpegBase64?: string
  telemetry?: Telemetry
  preflight?: CheckResult[]
  recentTurns?: { role: 'user' | 'brain'; text: string }[]
}

export interface BrainReply {
  speech: string
  driveIntent: DriveIntent | null
}
