/**
 * The embed module is the one source of truth for whether Drive is active.
 * Its getter and its subscribers change in the same turn as the message.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { driveActiveNow, subscribeDriveActive } from './driveActive'
import { enterFrame, leaveFrame, parentSays } from './testFrame'

beforeEach(() => {
  enterFrame()
})
afterEach(leaveFrame)

describe('the drive-active signal', () => {
  it('changes the getter and tells subscribers synchronously', () => {
    const seen: boolean[] = []
    const off = subscribeDriveActive(() => seen.push(driveActiveNow()))
    parentSays(true)
    expect(driveActiveNow()).toBe(true)
    parentSays(false)
    expect(driveActiveNow()).toBe(false)
    expect(seen).toEqual([true, false])
    off()
  })

  it('reaches every subscriber even when one of them fails', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const offBad = subscribeDriveActive(() => {
      throw new Error('a broken subscriber')
    })
    let told = false
    const offGood = subscribeDriveActive(() => {
      told = true
    })
    parentSays(true)
    expect(told).toBe(true)
    expect(error).toHaveBeenCalled()
    offBad()
    offGood()
    error.mockRestore()
  })
})
