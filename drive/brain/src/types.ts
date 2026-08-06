// Mirror of the fields the cockpit's Telemetry contract exposes (web/src/contract/index.ts).
// Kept structural (not imported) so the brain service has no dependency on the web app.
export interface Telemetry {
  speedKmh: number
  gear: 'R' | 'N' | 'F'
  steerAngleDeg: number
  mode: 'MANUAL' | 'AUTO'
  armed: boolean
  safetyState: 'DRIVING' | 'STOPPED' | 'LATCHED'
  battery: { percent: number; runtimeMin: number }
  lights: { headlights: boolean; blinker: 'off' | 'left' | 'right' | 'hazard'; horn: boolean }
  recording: boolean
  linkRttMs: number
  tempC: number
  headingDeg: number
}

export type DriveAction = 'forward' | 'left' | 'right' | 'stop' | 'none'

export interface DriveIntent {
  action: DriveAction
  /** requested active duration in ms; the cockpit clamps this to MAX_DRIVE_MS */
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
