/**
 * The voice service, as this application reaches it.
 *
 * A separate service from the world model, on its own address, and the
 * only thing this file knows about it. Nothing here names a model or a
 * provider: which one answers is the gateway's business and this
 * application is not told.
 *
 * Every reply carries its text. The audio is optional and may be absent
 * when a deployment has no synthesiser, so the interface is built around
 * the text and treats the sound as the extra.
 */

// Aliased: this module exports its own `say`, for the typed exchange.
import { say as words } from '../ui/wording'

const VOICE_URL = import.meta.env.VITE_VOICE_URL ?? 'http://127.0.0.1:8300'

export type ExchangeKind = 'question' | 'order' | 'unclear'

export interface Exchange {
  exchange_id: string
  /** What the machine believes it heard. Printed, always. */
  heard: string
  /** What the machine says back. Printed, always. */
  spoken: string
  kind: ExchangeKind
  /** True only for an order, and an order always needs one. */
  needs_confirmation: boolean
  action: { machine: string; task_type: string; place: string } | null
  audio: string | null
  audio_format: string
}

export interface VoiceCapabilities {
  can_hear: boolean
  can_speak: boolean
  can_understand: boolean
  character: string
}

async function call<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${VOICE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  })
  if (!response.ok) {
    // The service's own refusal wording is preferred: it comes from that
    // service's data file and matches what the world model would say. The
    // local line is only for a response that carried no sentence at all.
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail ?? words.voice.unreachable)
  }
  return response.json() as Promise<T>
}

/**
 * What this deployment's voice can do. Asked once at startup so the
 * button is never offered when holding it down could not work.
 */
export async function capabilities(token: string): Promise<VoiceCapabilities> {
  return call<VoiceCapabilities>('/v1/voice/capabilities', token)
}

export async function listen(token: string, clip: Blob): Promise<Exchange> {
  const form = new FormData()
  form.append('audio', clip, 'clip.webm')
  return call<Exchange>('/v1/voice/listen', token, { method: 'POST', body: form })
}

/** The same exchange, typed. For a silent room or a dead microphone. */
export async function say(token: string, text: string): Promise<Exchange> {
  return call<Exchange>('/v1/voice/say', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

/** Answer a readback. The only call that causes anything to happen. */
export async function confirm(
  token: string,
  exchangeId: string,
  confirmed: boolean,
): Promise<Exchange> {
  return call<Exchange>('/v1/voice/confirm', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ exchange_id: exchangeId, confirmed }),
  })
}

/**
 * Play what the machine said.
 *
 * Best effort on purpose. A browser that refuses to autoplay, or a
 * deployment with no synthesiser, must not stop the operator reading the
 * reply, which is already on screen by the time this runs.
 */
export function play(exchange: Exchange): void {
  if (!exchange.audio) return
  try {
    const bytes = Uint8Array.from(atob(exchange.audio), (c) => c.charCodeAt(0))
    const url = URL.createObjectURL(new Blob([bytes], { type: `audio/${exchange.audio_format}` }))
    const audio = new Audio(url)
    audio.addEventListener('ended', () => URL.revokeObjectURL(url))
    void audio.play().catch(() => URL.revokeObjectURL(url))
  } catch {
    /* the text is the record; losing the sound loses nothing that matters */
  }
}

/**
 * Push to talk.
 *
 * Recording starts when the operator presses and stops when they let go.
 * Deliberately not voice-activated: an open microphone in a vehicle picks
 * up a conversation nobody meant to issue as an order.
 */
export class PushToTalk {
  private recorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private stream: MediaStream | null = null

  async start(): Promise<void> {
    if (this.recorder) return
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.chunks = []
    this.recorder = new MediaRecorder(this.stream)
    this.recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data)
    }
    this.recorder.start()
  }

  async stop(): Promise<Blob | null> {
    const recorder = this.recorder
    if (!recorder) return null
    const finished = new Promise<Blob>((resolve) => {
      recorder.onstop = () => resolve(new Blob(this.chunks, { type: 'audio/webm' }))
    })
    recorder.stop()
    const clip = await finished
    this.stream?.getTracks().forEach((track) => track.stop())
    this.recorder = null
    this.stream = null
    return clip.size > 0 ? clip : null
  }

  get recording(): boolean {
    return this.recorder !== null
  }
}
