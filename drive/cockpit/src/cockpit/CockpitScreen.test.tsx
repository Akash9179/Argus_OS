/**
 * Drive asserts nothing about a machine that it was not told.
 * The daemon's session facts carry no vehicle class, so none is shown.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CockpitScreen } from './CockpitScreen'
import { useVehicleStore } from '../state/store'
import { enterFrame, leaveFrame, parentSays } from '../embed/testFrame'

afterEach(cleanup)
beforeEach(() => useVehicleStore.getState().reset())

describe('the machine card', () => {
  it('shows no vehicle class the daemon never reported', () => {
    render(<CockpitScreen />)
    expect(screen.getByText('This machine')).toBeTruthy()
    expect(screen.queryByText(/\bUGV\b/)).toBeNull()
  })

})

describe('Esc inside the frame', () => {
  const postMessage = vi.fn()

  beforeEach(() => {
    postMessage.mockReset()
    Object.defineProperty(window, 'parent', { value: { postMessage }, configurable: true })
  })

  afterEach(() => {
    Object.defineProperty(window, 'parent', { value: window, configurable: true })
    Object.defineProperty(document, 'referrer', { value: '', configurable: true })
  })

  it('asks the page that framed it to return to the desktop, at that origin only', () => {
    Object.defineProperty(document, 'referrer', { value: 'http://c2.test:5173/some/path', configurable: true })
    render(<CockpitScreen />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(postMessage).toHaveBeenCalledWith({ type: 'argus.drive.escape' }, 'http://c2.test:5173')
  })

  it('posts nothing when it cannot tell who framed it', () => {
    render(<CockpitScreen />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(postMessage).not.toHaveBeenCalled()
  })

  it('posts nothing when it is not in a frame', () => {
    Object.defineProperty(window, 'parent', { value: window, configurable: true })
    Object.defineProperty(document, 'referrer', { value: 'http://c2.test:5173/', configurable: true })
    const spy = vi.spyOn(window, 'postMessage')
    render(<CockpitScreen />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})

describe('the ARM button', () => {
  it('says to release the throttle when that is why arming did nothing', () => {
    render(<CockpitScreen />)
    const st = useVehicleStore.getState()
    act(() => {
      st.estop()
      st.tick(0.05)
    })
    act(() => st.setStick(0, 0.5))
    fireEvent.click(screen.getByRole('button', { name: 'ARM' }))
    expect(useVehicleStore.getState().command.safety.arm).toBe(false)
    expect(screen.getByText('Release throttle and steering to arm.')).toBeTruthy()

    act(() => st.setStick(0, 0))
    expect(screen.queryByText('Release throttle and steering to arm.')).toBeNull()
    expect(screen.getByRole('button', { name: 'ARM' })).toBeTruthy()
  })

  it('says Drive is not the active screen when that is why arming did nothing', () => {
    enterFrame()
    try {
      act(() => parentSays(false))
      render(<CockpitScreen />)
      act(() => {
        useVehicleStore.getState().estop()
        useVehicleStore.getState().tick(0.05)
      })
      // the gamepad arm combo while C2 shows another screen
      act(() => useVehicleStore.getState().arm())
      expect(useVehicleStore.getState().command.safety.arm).toBe(false)
      expect(screen.getByText('Drive is not the active screen.')).toBeTruthy()
      act(() => parentSays(true))
      expect(screen.queryByText('Drive is not the active screen.')).toBeNull()
    } finally {
      leaveFrame()
    }
  })
})
