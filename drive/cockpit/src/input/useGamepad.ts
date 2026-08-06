import { useEffect, useState } from 'react'
import { useVehicleStore } from '../state/store'
import { readGamepad, pressedSnapshot } from './dualsense'

export interface GamepadStatus {
  connected: boolean
  id: string
}

/** Polls a connected DualSense (or any standard gamepad) each frame and drives
 *  the vehicle store — the SAME actions the on-screen joystick uses. While a pad
 *  is connected it is authoritative (releasing the stick returns throttle to 0). */
export function useGamepad(): GamepadStatus {
  const [status, setStatus] = useState<GamepadStatus>({ connected: false, id: '' })

  useEffect(() => {
    let raf = 0
    let prev: boolean[] = []
    let wasConnected = false
    const s = useVehicleStore.getState() // actions are stable references

    const firstPad = () => {
      const pads = navigator.getGamepads ? navigator.getGamepads() : []
      for (const p of pads) if (p) return p
      return null
    }

    const loop = () => {
      const gp = firstPad()
      const connected = !!gp
      if (connected !== wasConnected) {
        wasConnected = connected
        setStatus({ connected, id: gp?.id ?? '' })
        if (!connected) prev = []
      }
      if (gp) {
        const r = readGamepad(gp, prev)
        s.setStick(r.steer, r.throttle)
        if (r.gear) s.setGear(r.gear)
        if (r.blinker) s.setBlinker(r.blinker)
        if (r.toggleLights) s.toggleHeadlights()
        if (r.toggleHorn) s.toggleHorn()
        if (r.toggleRecord) s.toggleRecord()
        if (r.arm) s.arm()
        if (r.estop) s.estop()
        prev = pressedSnapshot(gp)
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])

  return status
}
