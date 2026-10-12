/**
 * Drive asserts nothing about a machine that it was not told.
 * The daemon's session facts carry no vehicle class, so none is shown.
 */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { CockpitScreen } from './CockpitScreen'

afterEach(cleanup)

describe('the machine card', () => {
  it('shows no vehicle class the daemon never reported', () => {
    render(<CockpitScreen />)
    expect(screen.getByText('This machine')).toBeTruthy()
    expect(screen.queryByText(/\bUGV\b/)).toBeNull()
  })

})
