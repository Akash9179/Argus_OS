import { zodOutputFormat } from '@anthropic-ai/sdk/helpers/zod'
import { BrainReplySchema } from './reply-schema.ts'
import type { BrainTurn, BrainReply } from './types.ts'

const SYSTEM = `You are Argus, the onboard mind of a small autonomous ground vehicle.
You speak briefly, calmly, and competently — a capable co-pilot, not a chatbot.
You can SEE through the camera frame when one is provided: describe only what is
actually visible. When asked to run a pre-flight, read the provided checklist
results and summarize them plainly, calling out any warn/fail item.

You may propose a SINGLE bounded drive action via driveIntent when the operator
clearly asks you to move ('nudge forward', 'turn left a little', 'stop').
Otherwise driveIntent MUST be null. You never drive on your own initiative.
Keep 'speech' to one or two sentences.`

// Structural seam: method syntax (bivariant params) + `any` params + `unknown`
// result so the real @anthropic-ai/sdk client and a test fake both satisfy it.
// The zodOutputFormat schema + the cockpit-side isBrainReply guard enforce the
// shape at runtime, so the cast below is safe.
interface ParseClient {
  messages: {
    parse(params: any): Promise<{ parsed_output: unknown }>
  }
}

export function createAnthropicBrain(client: ParseClient) {
  return {
    async generate(turn: BrainTurn): Promise<BrainReply> {
      const userContent: Array<Record<string, unknown>> = []
      if (turn.cameraFrameJpegBase64) {
        userContent.push({
          type: 'image',
          source: { type: 'base64', media_type: 'image/jpeg', data: turn.cameraFrameJpegBase64 },
        })
      }
      const context = {
        telemetry: turn.telemetry ?? null,
        preflight: turn.preflight ?? null,
        recentTurns: turn.recentTurns ?? [],
      }
      userContent.push({
        type: 'text',
        text: `Operator said: ${turn.transcript}\n\nContext (JSON): ${JSON.stringify(context)}`,
      })

      const res = await client.messages.parse({
        model: 'claude-opus-5',
        max_tokens: 16000,
        system: SYSTEM,
        messages: [{ role: 'user', content: userContent }],
        output_config: { format: zodOutputFormat(BrainReplySchema) },
      })

      if (!res.parsed_output) throw new Error('brain: model returned no parseable output')
      return res.parsed_output as BrainReply
    },
  }
}
