import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ARM_CONFIRM_MS, useVehicleStore } from './store'
import { enterFrame, leaveFrame, parentSays } from '../embed/testFrame'
import type { PreflightState, SafetyState } from '../contract'

function reset() {
  useVehicleStore.getState().reset()
}

describe('vehicle store', () => {
  beforeEach(reset)

  it('setStick + ticks raise speed above 0', () => {
    const { setStick, tick } = useVehicleStore.getState()
    setStick(0, 1)
    for (let i = 0; i < 20; i++) tick(0.05)
    expect(useVehicleStore.getState().telemetry.speedKmh).toBeGreaterThan(0)
  })

  it('estop then tick latches safetyState', () => {
    const { estop, tick } = useVehicleStore.getState()
    estop()
    tick(0.05)
    expect(useVehicleStore.getState().telemetry.safetyState).toBe('LATCHED')
  })

  it('momentary safety edges reset after tick', () => {
    const { estop, tick } = useVehicleStore.getState()
    estop()
    expect(useVehicleStore.getState().command.safety.estop).toBe(true)
    tick(0.05)
    expect(useVehicleStore.getState().command.safety.estop).toBe(false)
  })

  it('setStick clamps to valid ranges', () => {
    const { setStick } = useVehicleStore.getState()
    setStick(5, 5)
    expect(useVehicleStore.getState().command.steer).toBe(1)
    expect(useVehicleStore.getState().command.throttle).toBe(1)
    setStick(-5, -5)
    expect(useVehicleStore.getState().command.steer).toBe(-1)
    expect(useVehicleStore.getState().command.throttle).toBe(0)
  })

  it('toggleRecord flips record', () => {
    const { toggleRecord } = useVehicleStore.getState()
    const before = useVehicleStore.getState().command.aux.record
    toggleRecord()
    expect(useVehicleStore.getState().command.aux.record).toBe(!before)
  })

  it('remembers when recording began, and forgets it when recording stops', () => {
    const { toggleRecord, tick, applyRemoteTelemetry } = useVehicleStore.getState()
    // a fresh cockpit records by default
    expect(useVehicleStore.getState().recordingSince).not.toBeNull()
    toggleRecord()
    tick(0.05)
    expect(useVehicleStore.getState().recordingSince).toBeNull()
    toggleRecord()
    tick(0.05)
    const since = useVehicleStore.getState().recordingSince
    expect(since).not.toBeNull()
    tick(0.05)
    expect(useVehicleStore.getState().recordingSince).toBe(since)
    applyRemoteTelemetry({ ...useVehicleStore.getState().telemetry, recording: false })
    expect(useVehicleStore.getState().recordingSince).toBeNull()
  })

  it('relinquish zeroes steer and throttle and drops the arm', () => {
    const { setStick, arm, relinquish } = useVehicleStore.getState()
    setStick(0.6, 0.8)
    arm()
    relinquish()
    const { command } = useVehicleStore.getState()
    expect(command.steer).toBe(0)
    expect(command.throttle).toBe(0)
    expect(command.safety.arm).toBe(false)
  })

  it('holds the operator arm across ticks until stop, relinquish, or the vehicle leaves DRIVING', () => {
    const st = () => useVehicleStore.getState()
    st().arm()
    st().tick(0.05)
    st().tick(0.05)
    expect(st().command.safety.arm).toBe(true)
    st().estop()
    expect(st().command.safety.arm).toBe(false)

    st().tick(0.05)
    st().arm()
    st().relinquish()
    expect(st().command.safety.arm).toBe(false)

    // late telemetry that has not caught up yet keeps the arm
    st().applyRemoteTelemetry({ ...st().telemetry, safetyState: 'STOPPED' })
    st().arm()
    st().applyRemoteTelemetry({ ...st().telemetry, safetyState: 'STOPPED' })
    expect(st().command.safety.arm).toBe(true)
    st().applyRemoteTelemetry({ ...st().telemetry, safetyState: 'DRIVING' })
    expect(st().command.safety.arm).toBe(true)
    // the vehicle disarmed or latched: re-arming is the operator's, never ours
    st().applyRemoteTelemetry({ ...st().telemetry, safetyState: 'LATCHED' })
    expect(st().command.safety.arm).toBe(false)
  })

  it('counts each accepted arm press, so a transport sees a fresh press', () => {
    const before = useVehicleStore.getState().armPresses
    useVehicleStore.getState().arm()
    useVehicleStore.getState().arm()
    expect(useVehicleStore.getState().armPresses).toBe(before + 2)
  })

  it('ignores arm while Drive is not the active screen, says why, and stop still works', () => {
    const st = () => useVehicleStore.getState()
    enterFrame()
    try {
      parentSays(false)
      st().arm()
      expect(st().command.safety.arm).toBe(false)
      expect(st().armRefusal).toBe('inactive')
      st().estop()
      expect(st().command.safety.estop).toBe(true)
      st().tick(0.05)
      // coming back clears the refusal; the operator arms again
      parentSays(true)
      expect(st().armRefusal).toBeNull()
      st().arm()
      expect(st().command.safety.arm).toBe(true)
    } finally {
      leaveFrame()
    }
  })

  it('refuses to arm with the throttle held or the steering off centre, and says why', () => {
    const st = () => useVehicleStore.getState()
    const presses = st().armPresses
    st().setStick(0, 0.5)
    st().arm()
    expect(st().command.safety.arm).toBe(false)
    expect(st().armPresses).toBe(presses)
    expect(st().armRefusal).toBe('stick')

    st().setStick(0.4, 0)
    st().arm()
    expect(st().command.safety.arm).toBe(false)

    st().setStick(0, 0)
    expect(st().armRefusal).toBeNull()
    st().arm()
    expect(st().command.safety.arm).toBe(true)
  })

  it("times the vehicle's recording from its own report, not from page load", () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(1_000_000)
      useVehicleStore.getState().reset()
      vi.setSystemTime(1_060_000)
      const st = useVehicleStore.getState()
      st.setRemote(true)
      st.applyRemoteTelemetry({ ...st.telemetry, recording: true })
      expect(useVehicleStore.getState().recordingSince).toBe(1_060_000)
    } finally {
      vi.useRealTimers()
    }
  })
})

const PASS: PreflightState = { ran: true, pass: true, checks: [{ name: 'mcu', ok: true, detail: '' }] }
const FAIL: PreflightState = { ran: true, pass: false, checks: [{ name: 'mcu', ok: false, detail: '' }] }

/** A bridge link with fresh vehicle telemetry: ignition and self-test as given. */
function onVehicle(ignition: boolean, preflight: PreflightState, safetyState: SafetyState = 'STOPPED') {
  const st = useVehicleStore.getState()
  st.setLinked(true)
  st.setRemote(true)
  st.applyPreflight(preflight)
  st.applyRemoteTelemetry({ ...st.telemetry, ignition, safetyState })
}

const reading = (safetyState: SafetyState) => {
  const st = useVehicleStore.getState()
  st.applyRemoteTelemetry({ ...st.telemetry, safetyState })
}

describe('the arm gate on a vehicle link', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    reset()
  })
  afterEach(() => vi.useRealTimers())
  const st = () => useVehicleStore.getState()

  it('refuses an arm from any source until the self-test passed', () => {
    onVehicle(true, FAIL)
    const presses = st().armPresses
    st().arm()
    expect(st().command.safety.arm).toBe(false)
    expect(st().armPresses).toBe(presses)
  })

  it('refuses an arm while the ignition is off', () => {
    onVehicle(false, PASS)
    st().arm()
    expect(st().command.safety.arm).toBe(false)
  })

  it('refuses an arm without fresh vehicle telemetry', () => {
    onVehicle(true, PASS)
    st().setRemote(false)
    st().arm()
    expect(st().command.safety.arm).toBe(false)
  })

  it('never arms later from a refused press when the self-test then passes', () => {
    onVehicle(true, FAIL)
    st().arm()
    st().applyPreflight(PASS)
    reading('STOPPED')
    vi.advanceTimersByTime(100)
    st().settleArm()
    st().tick(0.05)
    expect(st().command.safety.arm).toBe(false)
    // a fresh press is honoured
    st().arm()
    expect(st().command.safety.arm).toBe(true)
  })

  it('drops an arm request the vehicle never confirms', () => {
    onVehicle(true, PASS)
    st().arm()
    expect(st().command.safety.arm).toBe(true)
    // readings still in flight from before the press do not cancel it
    vi.advanceTimersByTime(ARM_CONFIRM_MS / 2)
    reading('STOPPED')
    st().settleArm()
    expect(st().command.safety.arm).toBe(true)
    vi.advanceTimersByTime(ARM_CONFIRM_MS / 2)
    st().settleArm()
    expect(st().command.safety.arm).toBe(false)
    // a late DRIVING reading does not bring it back
    reading('DRIVING')
    expect(st().command.safety.arm).toBe(false)
  })

  it('expires an unconfirmed request on the drive loop too', () => {
    onVehicle(true, PASS)
    st().arm()
    vi.advanceTimersByTime(ARM_CONFIRM_MS)
    st().tick(0.05)
    expect(st().command.safety.arm).toBe(false)
  })

  it('holds a confirmed arm while the vehicle reads DRIVING', () => {
    onVehicle(true, PASS)
    st().arm()
    reading('DRIVING')
    for (let i = 0; i < 50; i++) {
      vi.advanceTimersByTime(100)
      st().settleArm()
      st().tick(0.05)
      reading('DRIVING')
    }
    expect(st().command.safety.arm).toBe(true)
  })

  it.each(['STOPPED', 'LATCHED'] as const)('ends a confirmed arm on any %s reading', (state) => {
    onVehicle(true, PASS)
    st().arm()
    reading('DRIVING')
    reading(state)
    expect(st().command.safety.arm).toBe(false)
    reading('DRIVING')
    expect(st().command.safety.arm).toBe(false)
  })
})

describe('who latched it', () => {
  beforeEach(reset)
  const st = () => useVehicleStore.getState()

  it('claims a latch for the operator only after their STOP reached a live link', () => {
    onVehicle(true, PASS, 'DRIVING')
    st().estop()
    reading('LATCHED')
    expect(st().operatorStop).toBe('seen')
    // the vehicle moves on: the claim ends with the latch
    reading('STOPPED')
    expect(st().operatorStop).toBeNull()
  })

  it('does not claim a latch for a STOP pressed while the link was down', () => {
    onVehicle(true, PASS, 'DRIVING')
    st().loseLink()
    st().setRemote(false)
    st().estop()
    st().setRemote(true)
    reading('LATCHED')
    expect(st().operatorStop).toBeNull()
  })

  it('turns the ignition command off on link loss', () => {
    st().toggleIgnition()
    st().loseLink()
    expect(st().command.aux.ignition).toBe(false)
  })
})
