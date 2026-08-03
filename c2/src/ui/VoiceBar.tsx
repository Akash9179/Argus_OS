/**
 * The voice bar.
 *
 * Hold the button, or hold space, and talk. What the machine heard and
 * what it said are both printed here, always, because the honesty law
 * requires that spoken output is also shown as text and because an
 * operator in a loud vehicle cannot rely on hearing the reply.
 *
 * An order never happens on speech alone. When the machine reads an order
 * back, this bar shows the readback with two buttons and does nothing
 * until one of them is pressed. There is no timeout that says yes.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { savedToken } from '../sdk/client'
import * as voice from '../sdk/voice'
import { say } from './wording'

interface Props {
  /**
   * A message from elsewhere in the application: a refused order, a mode
   * change. This bar is the one message line on the screen, so those
   * still belong here. A live exchange takes precedence, because what the
   * operator just said is more urgent than what happened before it.
   */
  notice?: string
  /**
   * Told when an order goes through. The map does not need this to
   * update: it is driven by the world model's live stream and will show
   * the machine moving on its own. This is for anything the bar cannot
   * know about, such as clearing a stale notice.
   */
  onOrdered?: () => void
}

type Status = 'idle' | 'listening' | 'thinking'

export function VoiceBar({ notice, onOrdered }: Props) {
  // The same credential the rest of the application uses. The voice
  // service holds none of its own and acts only as the signed-in
  // operator, so an order it issues is that person's order.
  const token = savedToken() ?? ''
  const [capabilities, setCapabilities] = useState<voice.VoiceCapabilities | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [exchange, setExchange] = useState<voice.Exchange | null>(null)
  const [pending, setPending] = useState<voice.Exchange | null>(null)
  const [trouble, setTrouble] = useState<string>('')
  const ptt = useRef(new voice.PushToTalk())

  useEffect(() => {
    let alive = true
    voice
      .capabilities(token)
      .then((found) => alive && setCapabilities(found))
      // A voice service that is not running is not an error worth
      // shouting about. The map is the primary surface and it still works.
      .catch(() => alive && setCapabilities(null))
    return () => {
      alive = false
    }
  }, [token])

  const usable = Boolean(capabilities?.can_hear && capabilities?.can_understand)

  const finish = useCallback(
    (result: voice.Exchange) => {
      setExchange(result)
      voice.play(result)
      setPending(result.needs_confirmation ? result : null)
      setStatus('idle')
    },
    [],
  )

  const begin = useCallback(async () => {
    if (!usable || status !== 'idle') return
    setTrouble('')
    try {
      await ptt.current.start()
      setStatus('listening')
    } catch {
      setTrouble(say.voice.noMicrophone)
    }
  }, [usable, status])

  const end = useCallback(async () => {
    if (status !== 'listening') return
    setStatus('thinking')
    try {
      const clip = await ptt.current.stop()
      if (!clip) {
        setStatus('idle')
        return
      }
      finish(await voice.listen(token, clip))
    } catch (error) {
      setTrouble(error instanceof Error ? error.message : say.voice.unreachable)
      setStatus('idle')
    }
  }, [status, token, finish])

  // Space is the push-to-talk key, so it must not also scroll the page or
  // re-trigger on the operating system's key repeat.
  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.repeat) return
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return
      event.preventDefault()
      void begin()
    }
    const up = (event: KeyboardEvent) => {
      if (event.code !== 'Space') return
      event.preventDefault()
      void end()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [begin, end])

  const answer = useCallback(
    async (confirmed: boolean) => {
      if (!pending) return
      setPending(null)
      setStatus('thinking')
      try {
        const result = await voice.confirm(token, pending.exchange_id, confirmed)
        setExchange(result)
        voice.play(result)
        if (confirmed) onOrdered?.()
      } catch (error) {
        setTrouble(error instanceof Error ? error.message : say.voice.unreachable)
      } finally {
        setStatus('idle')
      }
    },
    [pending, token, onOrdered],
  )

  const line = trouble || describe(status, exchange, capabilities, notice)

  return (
    <div className="voicebar">
      <button
        className={`ptt ${status === 'listening' ? 'live' : ''}`}
        disabled={!usable || status === 'thinking'}
        title={usable ? say.voice.hold : say.voice.unavailable}
        aria-label={say.voice.hold}
        onPointerDown={() => void begin()}
        onPointerUp={() => void end()}
        onPointerLeave={() => void end()}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0" />
          <line x1="12" y1="18" x2="12" y2="21" />
        </svg>
      </button>

      <div className="voicelines">
        {/* Printed before the reply, and kept there, so an operator can
            see what the machine misheard when the answer is strange. */}
        {exchange?.heard ? <p className="heard">{say.voice.youSaid}{exchange.heard}</p> : null}
        <p className="said">{line}</p>
      </div>

      {pending ? (
        <div className="readback" role="group" aria-label={say.voice.confirmLabel}>
          <button className="confirm" onClick={() => void answer(true)}>
            {say.voice.yes}
          </button>
          <button className="cancel" onClick={() => void answer(false)}>
            {say.voice.no}
          </button>
        </div>
      ) : null}
    </div>
  )
}

/**
 * The one line the bar shows when there is nothing else to say.
 *
 * Never blank: a silent voice bar reads as a broken one, and an operator
 * needs to know whether holding the button will do anything.
 */
function describe(
  status: Status,
  exchange: voice.Exchange | null,
  capabilities: voice.VoiceCapabilities | null,
  notice?: string,
): string {
  if (status === 'listening') return say.voice.listening
  if (status === 'thinking') return say.voice.thinking
  if (exchange?.spoken) return exchange.spoken
  if (notice) return notice
  if (!capabilities) return say.voice.unreachable
  if (!capabilities.can_hear || !capabilities.can_understand) return say.voice.unavailable
  return say.voice.hold
}
