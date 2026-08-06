import { createServer } from 'node:http'
import type { ServerResponse } from 'node:http'
import Anthropic from '@anthropic-ai/sdk'
import { createAnthropicBrain } from './anthropic-brain.ts'
import type { BrainTurn } from './types.ts'

const brain = createAnthropicBrain(new Anthropic())
const PORT = Number(process.env.BRAIN_PORT ?? 8099)

function send(res: ServerResponse, code: number, body: unknown) {
  const data = JSON.stringify(body)
  res.writeHead(code, {
    'content-type': 'application/json',
    'access-control-allow-origin': process.env.BRAIN_CORS_ORIGIN ?? '*',
    'access-control-allow-headers': 'content-type',
    'access-control-allow-methods': 'POST, OPTIONS',
  })
  res.end(data)
}

const server = createServer((req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, {})
  if (req.method === 'GET' && req.url === '/health') return send(res, 200, { ok: true })
  if (req.method === 'POST' && req.url === '/brain/turn') {
    let raw = ''
    req.on('data', (c) => (raw += c))
    req.on('end', async () => {
      try {
        const turn = JSON.parse(raw) as BrainTurn
        if (typeof turn.transcript !== 'string') return send(res, 400, { error: 'transcript required' })
        const reply = await brain.generate(turn)
        send(res, 200, reply)
      } catch (err) {
        send(res, 500, { error: String(err instanceof Error ? err.message : err) })
      }
    })
    return
  }
  send(res, 404, { error: 'not found' })
})

server.listen(PORT, () => console.log(`[brain] listening on :${PORT}`))
