import { useEffect, useState } from 'react'
import { applyDeadzone } from './dualsense'

export interface GamepadMonitor {
  connected: boolean
  id: string
  lx: number // left stick X (raw -1..1)
  ly: number // left stick Y (raw -1..1)
  r2: number // 0..1
  l2: number // 0..1
  steer: number // mapped, deadzoned
  throttle: number // mapped 0..1
  pressed: boolean[] // per-button pressed
  buttonCount: number
}

const EMPTY: GamepadMonitor = {
  connected: false,
  id: '',
  lx: 0,
  ly: 0,
  r2: 0,
  l2: 0,
  steer: 0,
  throttle: 0,
  pressed: [],
  buttonCount: 0,
}

/** Read-only live gamepad snapshot for the Controller test panel. Does NOT
 *  dispatch to the store (useGamepad already does the driving). Only polls
 *  while `active` (e.g. the panel is open) to avoid extra work. */
export function useGamepadMonitor(active: boolean): GamepadMonitor {
  const [mon, setMon] = useState<GamepadMonitor>(EMPTY)

  useEffect(() => {
    if (!active) return
    let raf = 0
    const loop = () => {
      const pads = navigator.getGamepads ? navigator.getGamepads() : []
      let gp: Gamepad | null = null
      for (const p of pads) if (p) { gp = p; break }
      if (gp) {
        const r2 = gp.buttons[7]?.value ?? 0
        const l2 = gp.buttons[6]?.value ?? 0
        setMon({
          connected: true,
          id: gp.id,
          lx: gp.axes[0] ?? 0,
          ly: gp.axes[1] ?? 0,
          r2,
          l2,
          steer: applyDeadzone(gp.axes[0] ?? 0),
          throttle: Math.max(0, Math.min(1, r2 - l2)),
          pressed: gp.buttons.map((b) => !!b.pressed),
          buttonCount: gp.buttons.length,
        })
      } else {
        setMon((m) => (m.connected ? EMPTY : m))
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [active])

  return mon
}
