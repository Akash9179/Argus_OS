import { describe, it, expect, vi } from 'vitest'
import { createAnthropicBrain } from '../src/anthropic-brain.ts'
import type { BrainTurn } from '../src/types.ts'

function fakeClient(reply = { speech: 'Hello, operator.', driveIntent: null }) {
  const parse = vi.fn().mockResolvedValue({ parsed_output: reply })
  return { client: { messages: { parse } }, parse }
}

describe('createAnthropicBrain', () => {
  it('returns the parsed reply for a text-only turn', async () => {
    const { client } = fakeClient()
    const brain = createAnthropicBrain(client as never)
    const turn: BrainTurn = { transcript: 'Hi there' }
    const reply = await brain.generate(turn)
    expect(reply.speech).toBe('Hello, operator.')
    expect(reply.driveIntent).toBeNull()
  })

  it('includes a base64 image block when a camera frame is present', async () => {
    const { client, parse } = fakeClient()
    const brain = createAnthropicBrain(client as never)
    await brain.generate({ transcript: 'what do you see?', cameraFrameJpegBase64: 'QUJD' })
    const params = parse.mock.calls[0][0]
    const userContent = params.messages.at(-1).content
    const imageBlock = userContent.find((b: { type: string }) => b.type === 'image')
    expect(imageBlock).toBeTruthy()
    expect(imageBlock.source).toMatchObject({ type: 'base64', media_type: 'image/jpeg', data: 'QUJD' })
    expect(params.model).toBe('claude-opus-5')
  })

  it('throws when the model returns no parseable output', async () => {
    const parse = vi.fn().mockResolvedValue({ parsed_output: null })
    const brain = createAnthropicBrain({ messages: { parse } } as never)
    await expect(brain.generate({ transcript: 'hi' })).rejects.toThrow(/parse/i)
  })
})
