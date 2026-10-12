import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useVehicleStore } from './store'

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

  it('ignores arm while Drive is not the active screen, but stop still works', () => {
    const st = () => useVehicleStore.getState()
    st().setDriveActive(false)
    try {
      st().arm()
      expect(st().command.safety.arm).toBe(false)
      st().estop()
      expect(st().command.safety.estop).toBe(true)
    } finally {
      st().setDriveActive(true)
    }
    st().tick(0.05)
    st().arm()
    expect(st().command.safety.arm).toBe(true)
  })

  it('refuses to arm with the throttle held or the steering off centre, and says why', () => {
    const st = () => useVehicleStore.getState()
    const presses = st().armPresses
    st().setStick(0, 0.5)
    st().arm()
    expect(st().command.safety.arm).toBe(false)
    expect(st().armPresses).toBe(presses)
    expect(st().armBlocked).toBe(true)

    st().setStick(0.4, 0)
    st().arm()
    expect(st().command.safety.arm).toBe(false)

    st().setStick(0, 0)
    expect(st().armBlocked).toBe(false)
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
