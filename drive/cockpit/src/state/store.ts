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
  arm: () => void
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
  return { sim, command, telemetry, recordingSince: sinceRecording(null, telemetry) }
}

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
    set((s) => ({
      command: {
        ...s.command,
        steer: clampSigned(steer),
        throttle: clampUnit(throttle),
      },
    })),

  setGear: (g) => set((s) => ({ command: { ...s.command, gear: g } })),

  setMode: (m) => set((s) => ({ command: { ...s.command, mode: m } })),

  toggleIgnition: () =>
    set((s) => ({
      command: {
        ...s.command,
        aux: { ...s.command.aux, ignition: !s.command.aux.ignition },
      },
    })),

  setRemote: (on) => set({ remote: on }),

  // While a bridge link is live, the vehicle's own telemetry is the truth;
  // the local sim keeps ticking (it feeds nothing) but must not fight it.
  applyRemoteTelemetry: (t) =>
    set((s) => ({ telemetry: t, recordingSince: sinceRecording(s.recordingSince, t) })),

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
    set((s) => ({
      command: { ...s.command, safety: { ...s.command.safety, arm: true } },
    })),

  estop: () =>
    set((s) => ({
      command: { ...s.command, safety: { ...s.command.safety, estop: true } },
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
      // Clear momentary safety edges AFTER stepping.
      const command: Command = {
        ...s.command,
        safety: { arm: false, estop: false },
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
