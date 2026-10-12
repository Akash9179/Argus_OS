import { create } from 'zustand'
import { useEffect } from 'react'
import {
  clampSigned,
  clampUnit,
  neutralCommand,
  noPreflight,
  type Blinker,
  type Command,
  type DriveMode,
  type Gear,
  type PreflightState,
  type Telemetry,
} from '../contract'
import {
  initialSimState,
  stepVehicle,
  toTelemetry,
  type SimState,
} from '../mock/dummyVehicle'
import { driveActiveNow } from '../embed/driveActive'

interface VehicleStore {
  sim: SimState
  command: Command
  telemetry: Telemetry
  // actions
  setStick: (steer: number, throttle: number) => void
  setGear: (g: Gear) => void
  setMode: (m: DriveMode) => void
  toggleIgnition: () => void
  toggleHeadlights: () => void
  setBlinker: (b: Blinker) => void
  toggleHorn: () => void
  toggleRecord: () => void
  /**
   * The operator's arm. It holds (command.safety.arm stays true) until
   * STOP, relinquish, or the vehicle reports it left DRIVING. It is
   * refused while Drive is not the active screen, and while the throttle
   * is held or the steering is off centre.
   */
  arm: () => void
  /** Counts accepted arm presses, so a transport can tell a fresh press. */
  armPresses: number
  /** True when the last arm press was refused because the stick was not neutral. */
  armBlocked: boolean
  /** Whether Drive is the operator's active screen; set by the cockpit. */
  driveActive: boolean
  setDriveActive: (on: boolean) => void
  estop: () => void
  /** Leaving Drive: zero steer and throttle and drop the arm. Not a latched stop. */
  relinquish: () => void
  /** When the current recording began, by this cockpit's clock; null when not recording. */
  recordingSince: number | null
  remote: boolean
  preflight: PreflightState
  applyPreflight: (p: PreflightState) => void
  setRemote: (on: boolean) => void
  applyRemoteTelemetry: (t: Telemetry) => void
  tick: (dtSec: number) => void
  reset: () => void
}

function makeInitial() {
  const sim = initialSimState()
  const command = neutralCommand()
  const telemetry = toTelemetry(sim, command)
  return {
    sim,
    command,
    telemetry,
    recordingSince: sinceRecording(null, telemetry),
    armPresses: 0,
    armBlocked: false,
    driveActive: driveActiveNow(),
  }
}

const neutralStick = (c: Command) => c.throttle === 0 && c.steer === 0

/** Keep the first moment recording was seen on; clear it when recording stops. */
function sinceRecording(prev: number | null, t: Telemetry): number | null {
  if (!t.recording) return null
  return prev ?? Date.now()
}

export const useVehicleStore = create<VehicleStore>((set) => ({
  ...makeInitial(),
  remote: false,
  preflight: noPreflight(),

  setStick: (steer, throttle) =>
    set((s) => {
      const command = { ...s.command, steer: clampSigned(steer), throttle: clampUnit(throttle) }
      return { command, armBlocked: s.armBlocked && !neutralStick(command) }
    }),

  setGear: (g) => set((s) => ({ command: { ...s.command, gear: g } })),

  setMode: (m) => set((s) => ({ command: { ...s.command, mode: m } })),

  toggleIgnition: () =>
    set((s) => ({
      command: {
        ...s.command,
        aux: { ...s.command.aux, ignition: !s.command.aux.ignition },
      },
    })),

  // A new source of truth restarts the recording clock from its own report.
  setRemote: (on) => set((s) => (s.remote === on ? {} : { remote: on, recordingSince: null })),

  // While a bridge link is live, the vehicle's own telemetry is the truth;
  // the local sim keeps ticking (it feeds nothing) but must not fight it.
  // The vehicle leaving DRIVING (disarmed or latched) ends the operator's
  // arm: re-arming is the operator's act, never this cockpit's.
  applyRemoteTelemetry: (t) =>
    set((s) => {
      const fell = s.telemetry.safetyState === 'DRIVING' && t.safetyState !== 'DRIVING'
      return {
        telemetry: t,
        recordingSince: sinceRecording(s.recordingSince, t),
        ...(fell ? { command: { ...s.command, safety: { ...s.command.safety, arm: false } } } : {}),
      }
    }),

  applyPreflight: (p) => set({ preflight: p }),

  toggleHeadlights: () =>
    set((s) => ({
      command: {
        ...s.command,
        aux: { ...s.command.aux, headlights: !s.command.aux.headlights },
      },
    })),

  setBlinker: (b) =>
    set((s) => ({
      command: { ...s.command, aux: { ...s.command.aux, blinker: b } },
    })),

  toggleHorn: () =>
    set((s) => ({
      command: {
        ...s.command,
        aux: { ...s.command.aux, horn: !s.command.aux.horn },
      },
    })),

  toggleRecord: () =>
    set((s) => ({
      command: {
        ...s.command,
        aux: { ...s.command.aux, record: !s.command.aux.record },
      },
    })),

  arm: () =>
    set((s) => {
      if (!s.driveActive) return {}
      if (!neutralStick(s.command)) return { armBlocked: true }
      return {
        command: { ...s.command, safety: { ...s.command.safety, arm: true } },
        armPresses: s.armPresses + 1,
        armBlocked: false,
      }
    }),

  setDriveActive: (on) => set({ driveActive: on }),

  // STOP works whether or not Drive is the active screen.
  estop: () =>
    set((s) => ({
      command: { ...s.command, safety: { arm: false, estop: true } },
    })),

  relinquish: () =>
    set((s) => ({
      command: {
        ...s.command,
        steer: 0,
        throttle: 0,
        safety: { ...s.command.safety, arm: false },
      },
    })),

  tick: (dtSec) =>
    set((s) => {
      const sim = stepVehicle(s.sim, s.command, dtSec)
      const telemetry = s.remote ? s.telemetry : toTelemetry(sim, s.command)
      // Clear the momentary stop edge AFTER stepping. The arm holds.
      const command: Command = {
        ...s.command,
        safety: { arm: s.command.safety.arm, estop: false },
      }
      return { sim, command, telemetry, recordingSince: sinceRecording(s.recordingSince, telemetry) }
    }),

  reset: () => set(makeInitial()),
}))

export const useTelemetry = () => useVehicleStore((s) => s.telemetry)

export function useDriveLoop(hz = 20): void {
  const tick = useVehicleStore((s) => s.tick)
  useEffect(() => {
    const dt = 1 / hz
    const id = setInterval(() => tick(dt), dt * 1000)
    return () => clearInterval(id)
  }, [tick, hz])
}
