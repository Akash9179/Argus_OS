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
  type SafetyState,
  type Telemetry,
} from '../contract'
import {
  initialSimState,
  stepVehicle,
  toTelemetry,
  type SimState,
} from '../mock/dummyVehicle'
import { driveActiveNow, subscribeDriveActive } from '../embed/driveActive'

/**
 * How long a fresh arm press is asserted before the vehicle must confirm
 * DRIVING. The daemon reports telemetry at 10 Hz, so 500 ms is five
 * reports, room for a slow round trip. It is shorter than the daemon's
 * 700 ms watchdog window. An unconfirmed request is dropped; the operator
 * presses again.
 */
export const ARM_CONFIRM_MS = 500

/** Why the last arm press did nothing, when the operator can fix it. */
export type ArmRefusal = 'stick' | 'inactive' | null

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
   * The operator's arm press: a momentary request, not a latch. It is
   * refused while Drive is not the active screen, while the throttle is
   * held or the steering is off centre, and on a vehicle link unless fresh
   * telemetry reads ignition on and the self-test passed. The same gate
   * holds for the ARM button, the gamepad, and any other source.
   *
   * An accepted press is asserted for ARM_CONFIRM_MS. If the vehicle does
   * not read DRIVING in that window, the request is dropped. While it is
   * pending, a reading that moves to LATCHED or a state this cockpit does
   * not know drops it at once, and the transport sends zero throttle. Once
   * confirmed, it holds only while the vehicle reads DRIVING: any STOPPED
   * or LATCHED reading, STOP, or relinquish ends it.
   */
  arm: () => void
  /** Counts accepted arm presses, so a transport can tell a fresh press. */
  armPresses: number
  /** Why the last arm press did nothing, or null. */
  armRefusal: ArmRefusal
  /** When an unconfirmed arm request lapses, by Date.now(); null when none is pending. */
  armDeadline: number | null
  /** Drop an arm request that has outlived its window. Transports call it before each frame. */
  settleArm: () => void
  /** A bridge link to a vehicle is set up: its telemetry, not the local sim, is the truth. */
  linked: boolean
  setLinked: (on: boolean) => void
  estop: () => void
  /** Leaving Drive: zero steer and throttle and drop the arm. Not a latched stop. */
  relinquish: () => void
  /**
   * The vehicle link was lost or went stale: relinquish, and turn this
   * cockpit's ignition command off. Ignition is never replayed on
   * reconnect; the operator turns it on again.
   */
  loseLink: () => void
  /** When the current recording began, by this cockpit's clock; null when not recording. */
  recordingSince: number | null
  /**
   * This cockpit sent STOP and is waiting for the latch it causes ('sent'),
   * or the vehicle's latch followed it ('seen'). Null otherwise, and after
   * a link loss: then a latch may be the vehicle's own.
   */
  operatorStop: 'sent' | 'seen' | null
  /** Fresh telemetry from the vehicle is arriving: the link is live. */
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
    armRefusal: null as ArmRefusal,
    armDeadline: null as number | null,
    linked: false,
    operatorStop: null as VehicleStore['operatorStop'],
    remote: false,
    preflight: noPreflight(),
  }
}

const neutralStick = (c: Command) => c.throttle === 0 && c.steer === 0

/**
 * The vehicle-side half of the arm gate, shared by the ARM button and
 * arm(). Off a vehicle link (local simulation, Remo relay) there is no
 * self-test to wait for.
 */
export function armGateOpen(s: Pick<VehicleStore, 'linked' | 'remote' | 'telemetry' | 'preflight'>): boolean {
  if (!s.linked) return true
  return s.remote && s.telemetry.ignition && s.preflight.ran && s.preflight.pass
}

const dropArm = (c: Command): Command => ({ ...c, safety: { ...c.safety, arm: false } })

/**
 * An arm request the vehicle has not yet confirmed. While it is pending,
 * outgoing frames carry zero throttle: the request is not control yet.
 */
export function armPending(s: Pick<VehicleStore, 'command' | 'armDeadline'>): boolean {
  return s.command.safety.arm && s.armDeadline !== null
}

const KNOWN_STATES: readonly SafetyState[] = ['DRIVING', 'STOPPED', 'LATCHED']

/**
 * Apply one safety reading to the arm request. `reading` is null when
 * there is no word from the vehicle to apply, and only the window counts.
 * `previous` is the reading before this one.
 *
 * While a request is pending, STOPPED readings are normal: the vehicle
 * has not read the press yet, and telemetry lags a round trip. A LATCHED
 * reading that was already there before is normal for the same reason:
 * it is the latch this press is re-arming. A reading that moves to
 * LATCHED, or a state this cockpit does not know, ends the request at
 * once.
 */
function settle(
  s: Pick<VehicleStore, 'command' | 'armDeadline'>,
  reading: SafetyState | null,
  previous: SafetyState | null,
  now: number,
): Partial<Pick<VehicleStore, 'command' | 'armDeadline'>> {
  if (!s.command.safety.arm) return s.armDeadline === null ? {} : { armDeadline: null }
  if (reading === 'DRIVING') return s.armDeadline === null ? {} : { armDeadline: null }
  const confirmedThenLost = reading !== null && s.armDeadline === null
  const lapsed = s.armDeadline !== null && now >= s.armDeadline
  const refused =
    s.armDeadline !== null &&
    reading !== null &&
    (!KNOWN_STATES.includes(reading) || (reading === 'LATCHED' && previous !== 'LATCHED'))
  return confirmedThenLost || lapsed || refused ? { command: dropArm(s.command), armDeadline: null } : {}
}

/** Track whether a latch is the one the operator's own STOP caused. */
function stopCause(prev: VehicleStore['operatorStop'], reading: SafetyState): VehicleStore['operatorStop'] {
  if (prev === 'sent') return reading === 'LATCHED' ? 'seen' : 'sent'
  if (prev === 'seen') return reading === 'LATCHED' ? 'seen' : null
  return null
}

/** The reading that may confirm an arm without a remote frame: the local sim's, off a vehicle link. */
const localReading = (s: Pick<VehicleStore, 'linked' | 'telemetry'>): SafetyState | null =>
  s.linked ? null : s.telemetry.safetyState

/** Keep the first moment recording was seen on; clear it when recording stops. */
function sinceRecording(prev: number | null, t: Telemetry): number | null {
  if (!t.recording) return null
  return prev ?? Date.now()
}

export const useVehicleStore = create<VehicleStore>((set) => ({
  ...makeInitial(),

  setStick: (steer, throttle) =>
    set((s) => {
      const command = { ...s.command, steer: clampSigned(steer), throttle: clampUnit(throttle) }
      return { command, armRefusal: s.armRefusal === 'stick' && neutralStick(command) ? null : s.armRefusal }
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
  // A STOP pressed before it may never have reached the vehicle, so a
  // latch it reports is not claimed as the operator's.
  setRemote: (on) =>
    set((s) => (s.remote === on ? {} : { remote: on, recordingSince: null, operatorStop: null })),

  // While a bridge link is live, the vehicle's own telemetry is the truth;
  // the local sim keeps ticking (it feeds nothing) but must not fight it.
  // The vehicle's reading confirms or ends the operator's arm request:
  // re-arming is the operator's act, never this cockpit's.
  applyRemoteTelemetry: (t) =>
    set((s) => ({
      telemetry: t,
      recordingSince: sinceRecording(s.recordingSince, t),
      operatorStop: stopCause(s.operatorStop, t.safetyState),
      ...settle(s, t.safetyState, s.telemetry.safetyState, Date.now()),
    })),

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
      // Read at the moment of the press, never from a copy a render made.
      if (!driveActiveNow()) return { armRefusal: 'inactive' }
      if (!armGateOpen(s)) return {}
      if (!neutralStick(s.command)) return { armRefusal: 'stick' }
      return {
        command: { ...s.command, safety: { ...s.command.safety, arm: true } },
        armPresses: s.armPresses + 1,
        armRefusal: null,
        armDeadline: Date.now() + ARM_CONFIRM_MS,
      }
    }),

  // No new reading here: only the window counts, or the sim's standing state.
  settleArm: () =>
    set((s) => {
      const reading = localReading(s)
      return settle(s, reading, reading, Date.now())
    }),

  setLinked: (on) => set({ linked: on }),

  // STOP works whether or not Drive is the active screen.
  estop: () =>
    set((s) => ({
      command: { ...s.command, safety: { arm: false, estop: true } },
      armDeadline: null,
      operatorStop: 'sent',
    })),

  relinquish: () =>
    set((s) => ({
      command: {
        ...s.command,
        steer: 0,
        throttle: 0,
        safety: { ...s.command.safety, arm: false },
      },
      armDeadline: null,
    })),

  loseLink: () =>
    set((s) => ({
      command: {
        ...s.command,
        steer: 0,
        throttle: 0,
        aux: { ...s.command.aux, ignition: false },
        safety: { ...s.command.safety, arm: false },
      },
      armDeadline: null,
      operatorStop: null,
    })),

  tick: (dtSec) =>
    set((s) => {
      const sim = stepVehicle(s.sim, s.command, dtSec)
      const telemetry = s.remote ? s.telemetry : toTelemetry(sim, s.command)
      // Clear the momentary stop edge AFTER stepping.
      const command: Command = {
        ...s.command,
        safety: { arm: s.command.safety.arm, estop: false },
      }
      const next = { ...s, command, telemetry }
      return {
        sim,
        command,
        telemetry,
        recordingSince: sinceRecording(s.recordingSince, telemetry),
        ...(s.remote ? {} : { operatorStop: stopCause(s.operatorStop, telemetry.safetyState) }),
        ...settle(next, localReading(next), localReading(s), Date.now()),
      }
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

// Coming back to Drive clears the 'not the active screen' refusal.
subscribeDriveActive(() => {
  if (driveActiveNow() && useVehicleStore.getState().armRefusal === 'inactive')
    useVehicleStore.setState({ armRefusal: null })
})
