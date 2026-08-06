import { describe, it, expect, beforeEach } from 'vitest'
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
})
