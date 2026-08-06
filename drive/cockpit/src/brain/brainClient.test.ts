import { describe, it, expect, vi } from 'vitest'
import { postTurn, isBrainReply } from './brainClient'

describe('isBrainReply', () => {
  it('accepts a valid reply and rejects junk', () => {
    expect(isBrainReply({ speech: 'hi', driveIntent: null })).toBe(true)
    expect(isBrainReply({ speech: 'go', driveIntent: { action: 'forward' } })).toBe(true)
    expect(isBrainReply({ driveIntent: null })).toBe(false)
    expect(isBrainReply({ speech: 'x', driveIntent: { action: 'fly' } })).toBe(false)
  })
})

describe('postTurn', () => {
  it('posts the turn and returns the parsed reply', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ speech: 'On it.', driveIntent: { action: 'forward', durationMs: 800 } }),
    })
    const reply = await postTurn(
      { transcript: 'nudge forward' },
      { baseUrl: 'http://x', fetchImpl: fetchImpl as never },
    )
    expect(reply.driveIntent?.action).toBe('forward')
    expect(fetchImpl).toHaveBeenCalledWith('http://x/brain/turn', expect.objectContaining({ method: 'POST' }))
  })

  it('throws on a malformed reply shape', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ nope: 1 }) })
    await expect(
      postTurn({ transcript: 'hi' }, { baseUrl: 'http://x', fetchImpl: fetchImpl as never }),
    ).rejects.toThrow()
  })
})
