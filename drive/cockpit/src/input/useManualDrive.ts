import { useCallback, useEffect, useRef } from 'react'
import { useVehicleStore } from '../state/store'

/**
 * Keyboard + on-screen driving for when no gamepad is connected.
 *   ArrowLeft / ArrowRight → steer
 *   ArrowUp                → accelerate (throttle)
 *   ArrowDown              → brake / hold at stop
 * Hold to act, release returns to neutral — same model as the joystick spring.
 * The on-screen arrow pad calls press()/release() so both share one input model.
 */
export type DriveDir = 'left' | 'right' | 'up' | 'down'

const THROTTLE = 0.5 // moderate fixed throttle while accelerating
const STEER = 1.0

export function useManualDrive(enabled: boolean) {
  const active = useRef<Set<DriveDir>>(new Set())

  const apply = useCallback(() => {
    const a = active.current
    const steer = (a.has('right') ? STEER : 0) - (a.has('left') ? STEER : 0)
    const throttle = a.has('up') && !a.has('down') ? THROTTLE : 0
    useVehicleStore.getState().setStick(steer, throttle)
  }, [])

  const press = useCallback(
    (d: DriveDir) => {
      if (!active.current.has(d)) {
        active.current.add(d)
        apply()
      }
    },
    [apply],
  )

  const release = useCallback(
    (d: DriveDir) => {
      if (active.current.delete(d)) apply()
    },
    [apply],
  )

  const releaseAll = useCallback(() => {
    if (active.current.size) {
      active.current.clear()
      apply()
    }
  }, [apply])

  useEffect(() => {
    if (!enabled) {
      releaseAll()
      return
    }
    const map: Record<string, DriveDir> = {
      ArrowLeft: 'left',
      ArrowRight: 'right',
      ArrowUp: 'up',
      ArrowDown: 'down',
    }
    const isTyping = (t: EventTarget | null) => {
      const el = t as HTMLElement | null
      return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
    }
    const down = (e: KeyboardEvent) => {
      const d = map[e.key]
      if (!d || isTyping(e.target)) return
      e.preventDefault()
      press(d)
    }
    const up = (e: KeyboardEvent) => {
      const d = map[e.key]
      if (!d) return
      e.preventDefault()
      release(d)
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', releaseAll) // dropping focus = release the keys
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', releaseAll)
      releaseAll()
    }
  }, [enabled, press, release, releaseAll])

  return { press, release }
}
