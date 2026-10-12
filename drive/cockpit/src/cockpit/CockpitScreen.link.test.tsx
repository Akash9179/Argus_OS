/**
 * When the vehicle link is lost the screen says so plainly. It never shows
 * the local simulation's arm or ignition as if the vehicle reported them,
 * and it keeps the vehicle's last word on what it does on link loss.
 *
 * The bridge hook is mocked. Nothing here opens a socket.
 */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SessionFacts } from '../contract'
import type { BridgeLink } from '../transport/useBridgeTransport'

const link = vi.hoisted(() => ({ current: null as unknown as BridgeLink }))
vi.mock('../transport/useBridgeTransport', () => ({ useBridgeTransport: () => link.current }))

import { CockpitScreen } from './CockpitScreen'
import { useVehicleStore } from '../state/store'

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
    render(<CockpitScreen />)
    const pill = screen.getByText('LINK LOST')
    expect(pill.className).toContain('is-act')
    expect(screen.queryByText('DRIVING')).toBeNull()
    expect(screen.queryByText('Armed')).toBeNull()
    expect(screen.queryByText('Local simulation')).toBeNull()
    expect(screen.getByText('No reading')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /^\s*On$/ })).toBeNull()
    expect((screen.getByRole('button', { name: 'ARM' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it("keeps the vehicle's last sentence about link loss, marked as last reported", () => {
    link.current = lost(facts)
    render(<CockpitScreen />)
    expect(screen.getByText(/Bench mock stops itself after 700 ms/)).toBeTruthy()
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
})
