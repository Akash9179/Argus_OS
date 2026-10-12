/**
 * When the vehicle link is lost the screen says so plainly. It never shows
 * the local simulation's arm or ignition as if the vehicle reported them,
 * and it keeps the vehicle's last word on what it does on link loss.
 *
 * The bridge hook is mocked. Nothing here opens a socket.
 */
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SessionFacts } from '../contract'
import type { BridgeLink } from '../transport/useBridgeTransport'

const link = vi.hoisted(() => ({ current: null as unknown as BridgeLink, password: undefined as string | null | undefined }))
vi.mock('../transport/useBridgeTransport', () => ({
  useBridgeTransport: (password: string | null) => {
    link.password = password
    return link.current
  },
}))

import { CockpitScreen } from './CockpitScreen'
import { useVehicleStore } from '../state/store'
import { enterFrame, leaveFrame, parentSignsOut } from '../embed/testFrame'
import { getDriveKey, setDriveKey } from '../transport/auth'

const SINCE = new Date(2026, 9, 12, 9, 15).getTime()
const facts: SessionFacts = { role: 'DRIVER', driver: 'akash', vehicle: 'Bench mock', watchdogMs: 700, since: SINCE }

function lost(lastSession: SessionFacts | null): BridgeLink {
  return { active: true, label: 'x', status: 'closed', role: null, authFailed: false, session: null, lastSession, everOpen: true, hz: 15 }
}

beforeEach(() => {
  const st = useVehicleStore.getState()
  st.reset()
  // the local sim reads armed, and the cockpit has ignition on
  st.toggleIgnition()
  st.tick(0.05)
  expect(useVehicleStore.getState().telemetry.safetyState).toBe('DRIVING')
})
afterEach(cleanup)

describe('a lost link', () => {
  it('shows a red link lost state, never the local sim as armed or ignition on', () => {
    link.current = lost(facts)
    const { container } = render(<CockpitScreen />)
    const pill = screen.getByText('LINK LOST')
    expect(pill.className).toContain('is-act')
    expect(screen.queryByText('DRIVING')).toBeNull()
    expect(screen.queryByText('Armed')).toBeNull()
    expect(screen.queryByText('Local simulation')).toBeNull()
    expect(container.querySelector('.ign .pill')?.textContent?.trim()).toBe('No reading')
    expect(screen.queryByRole('button', { name: /^\s*On$/ })).toBeNull()
    expect((screen.getByRole('button', { name: 'ARM' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("keeps the vehicle's last sentence about link loss, marked as last reported", () => {
    link.current = lost(facts)
    render(<CockpitScreen />)
    // Only what this cockpit can stand behind: it sends no arm until the operator presses ARM.
    expect(
      screen.getByText(
        'Bench mock stops itself after 700 ms of silence. When the link returns, this cockpit sends no arm until you press ARM again.',
      ),
    ).toBeTruthy()
    expect(screen.queryByText(/stays stopped/)).toBeNull()
    expect(screen.getByText('Last reported at 09:15.')).toBeTruthy()
    expect(screen.queryByText(/has not said what it does on link loss/)).toBeNull()
  })

  it('falls back only when the vehicle never said', () => {
    link.current = lost(null)
    render(<CockpitScreen />)
    expect(screen.getByText(/has not said what it does on link loss/)).toBeTruthy()
  })

  it('shows the live sentence without a time while the link is open', () => {
    link.current = { ...lost(facts), status: 'open', session: facts }
    useVehicleStore.getState().setRemote(true)
    render(<CockpitScreen />)
    expect(screen.getByText(/Bench mock stops itself after 700 ms/)).toBeTruthy()
    expect(screen.queryByText(/Last reported/)).toBeNull()
    expect(screen.queryByText('LINK LOST')).toBeNull()
  })

  it('never shows Armed after a reconnect until fresh vehicle telemetry arrives', () => {
    // the socket is open again, but the vehicle has not spoken yet
    link.current = { ...lost(facts), status: 'open', session: facts }
    render(<CockpitScreen />)
    expect(screen.queryByText('Armed')).toBeNull()
    expect(screen.queryByText('DRIVING')).toBeNull()
    expect(screen.getByText('LINK LOST')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'ARM' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('blanks every HUD value under LINK LOST, never the local simulation', () => {
    const st = useVehicleStore.getState()
    // the local sim moves: speed, steer, heading, lights, gear
    st.toggleHeadlights()
    st.setStick(0.6, 1)
    for (let i = 0; i < 20; i++) st.tick(0.05)
    expect(useVehicleStore.getState().telemetry.speedKmh).toBeGreaterThan(0)
    link.current = lost(facts)
    const { container } = render(<CockpitScreen />)
    expect(screen.queryByText('km/h')).toBeNull()
    expect(container.querySelector('.speed')?.textContent).toBe('No reading')
    expect(container.querySelector('.heading')).toBeNull()
    expect(container.querySelector('.gear-hud')).toBeNull()
    expect(container.querySelector('.steer-arc')).toBeNull()
    expect(screen.queryByText(/^Steer /)).toBeNull()
    expect(container.querySelector('.rec')?.textContent).toBe('REC')
    expect(container.querySelectorAll('.gears button[aria-pressed="true"]').length).toBe(0)
    expect(screen.getByTitle('Headlights').getAttribute('aria-pressed')).toBe('false')
  })
})

describe('the safety state', () => {
  function live() {
    link.current = { ...lost(facts), status: 'open', session: facts }
    useVehicleStore.getState().setRemote(true)
  }
  const reading = (safetyState: string) => {
    const st = useVehicleStore.getState()
    act(() => st.applyRemoteTelemetry({ ...st.telemetry, safetyState }))
  }

  it('says the operator stopped it when the latch followed their own STOP', () => {
    live()
    render(<CockpitScreen />)
    act(() => useVehicleStore.getState().estop())
    // a reading already in flight still says DRIVING
    reading('DRIVING')
    reading('LATCHED')
    expect(screen.getByText('STOPPED BY YOU (LATCHED)')).toBeTruthy()
    expect(screen.queryByText(/stopped itself/i)).toBeNull()
  })

  it("keeps the vehicle's wording when the vehicle latched by itself", () => {
    live()
    render(<CockpitScreen />)
    reading('LATCHED')
    expect(screen.getByText('LATCHED: STOPPED ITSELF')).toBeTruthy()
    expect(screen.queryByText(/stopped by you/i)).toBeNull()
  })

  it("keeps the vehicle's wording for a latch that came after a link loss", () => {
    live()
    const view = render(<CockpitScreen />)
    act(() => useVehicleStore.getState().estop())
    act(() => useVehicleStore.getState().loseLink())
    reading('LATCHED')
    view.rerender(<CockpitScreen />)
    expect(screen.getByText('LATCHED: STOPPED ITSELF')).toBeTruthy()
  })

  it('shows a state it does not understand as itself, in a neutral tone', () => {
    live()
    render(<CockpitScreen />)
    reading('DOCKING')
    const pill = screen.getByText('DOCKING: STATE NOT UNDERSTOOD')
    expect(pill.className).toContain('is-off')
    expect(screen.queryByText(/stopped itself/i)).toBeNull()
  })
})

describe('sign-out from C2', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/?bridge=localhost:8090')
    enterFrame()
  })
  afterEach(() => {
    leaveFrame()
    window.history.replaceState(null, '', '/')
  })

  it('forgets the key the screen holds, in the same turn', () => {
    setDriveKey('operator-a')
    link.current = lost(facts)
    render(<CockpitScreen />)
    expect(link.password).toBe('operator-a')
    act(() => parentSignsOut())
    expect(getDriveKey()).toBeNull()
    expect(link.password).toBeNull()
  })
})
