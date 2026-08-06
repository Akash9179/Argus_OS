import { z } from 'zod'

export const BrainReplySchema = z.object({
  speech: z.string().describe('What the vehicle says back to the operator, in its own voice.'),
  driveIntent: z
    .object({
      action: z.enum(['forward', 'left', 'right', 'stop', 'none']),
      durationMs: z.number().optional(),
    })
    .nullable()
    .describe('A bounded drive action to perform, or null when the reply is conversational only.'),
})
