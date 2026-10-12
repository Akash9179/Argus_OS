/**
 * The assistant panel.
 *
 * Argus proposes; the operator approves. An order typed or spoken here goes
 * to the voice service, which works out what was meant and reads it back.
 * Before the readback is answered, the world model is asked what would
 * happen if the order were sent: the path, and a set of checks with their
 * sources. The operator sees all of that and then says yes or no. Nothing
 * moves on speech, on text, or on a timeout; only on the yes.
 *
 * What the machine heard and what it said are both printed, always: an
 * operator in a loud room cannot rely on hearing the reply, and a strange
 * answer has to be traceable to a mishearing rather than guessed at.
 *
 * The request carries the operator's words and nothing else. So the panel
 * names no machine and no place of its own; the only machine it shows is
 * the one the server resolved, on the proposal.
 *
 * When the voice service cannot be reached the panel says so, keeps asking,
 * and tells the screen, which folds it to its rail until the service
 * answers again.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { track as api, Refused } from '../sdk/client'
import { savedToken } from '../sdk/session'
import type { Position, TaskPreview } from '../sdk/types'
import * as voice from '../sdk/voice'
import { ArgusIcon } from './ArgusMark'
import { clockAt, plain, say } from './wording'

interface Message {
  who: 'you' | 'argus'
  text: string
  at: number
  /** For an operator's line: how it arrived. */
  how?: 'typed' | 'voice'
}

export interface Proposal {
  exchange: voice.Exchange
  preview: TaskPreview | null
  /** Set when the preview could not be fetched; the readback still stands. */
  previewTrouble: string
}

interface Props {
  collapsed: boolean
  onToggle: () => void
  /** The proposed path, for the map to draw; null when there is none. */
  onProposal: (path: Position[] | null) => void
  /** Told when an order goes through, so a stale notice elsewhere can clear. */
  onOrdered?: () => void
  /**
   * Told when the voice service stops or starts answering. Only on a
   * change, so a panel the operator opened by hand stays open while the
   * service is still unreachable.
   */
  onReach?: (reached: boolean) => void
}

type Status = 'idle' | 'listening' | 'thinking'

/** How long to wait before asking an unreachable voice service again. */
export const VOICE_RETRY_MS = 15_000

export function Assistant({ collapsed, onToggle, onProposal, onOrdered, onReach }: Props) {
  // The same credential the rest of the application uses. The voice
  // service holds none of its own and acts only as the signed-in operator,
  // so an order it issues is that person's order.
  const token = savedToken()
  const [capabilities, setCapabilities] = useState<voice.VoiceCapabilities | null | 'unreached'>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [messages, setMessages] = useState<Message[]>([])
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [showAllChecks, setShowAllChecks] = useState(false)
  const [draft, setDraft] = useState('')
  const [trouble, setTrouble] = useState('')
  const ptt = useRef(new voice.PushToTalk())
  const scroller = useRef<HTMLDivElement>(null)

  // Each attempt asks the service once. An unreachable service is asked
  // again after a pause, so the panel comes back when the service does.
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let alive = true
    voice
      .capabilities(token)
      .then((found) => alive && setCapabilities(found))
      // A voice service that is not running is not an error worth shouting
      // about. The map is the primary surface and it still works.
      .catch(() => alive && setCapabilities('unreached'))
    return () => {
      alive = false
    }
  }, [token, attempt])
  useEffect(() => {
    if (capabilities !== 'unreached') return
    const timer = window.setTimeout(() => setAttempt((n) => n + 1), VOICE_RETRY_MS)
    return () => window.clearTimeout(timer)
  }, [capabilities, attempt])

  // Reachability changes only on a transition, so the screen hears each
  // change once. Unknown (still asking) is not reported at all.
  const reached = capabilities === null ? null : capabilities !== 'unreached'
  const onReachRef = useRef(onReach)
  useLayoutEffect(() => {
    onReachRef.current = onReach
  })
  useEffect(() => {
    if (reached !== null) onReachRef.current?.(reached)
  }, [reached])

  useEffect(() => {
    // jsdom has no scrollTo; a browser always does.
    const el = scroller.current
    if (el && typeof el.scrollTo === 'function') el.scrollTo({ top: el.scrollHeight })
  }, [messages, proposal])

  const canUnderstand = capabilities !== null && capabilities !== 'unreached' && capabilities.can_understand
  const canHear = canUnderstand && (capabilities as voice.VoiceCapabilities).can_hear

  const push = (message: Message) => setMessages((m) => [...m, message])

  /**
   * An exchange came back. Print it, and if it is an order awaiting a
   * readback, ask the world model what sending it would mean.
   */
  const took = useCallback(
    async (exchange: voice.Exchange) => {
      push({ who: 'argus', text: exchange.spoken, at: Date.now() / 1000 })
      voice.play(exchange)
      if (!exchange.needs_confirmation) {
        setProposal(null)
        onProposal(null)
        return
      }
      const action = exchange.action
      let preview: TaskPreview | null = null
      let previewTrouble = ''
      if (action?.asset_id) {
        try {
          preview = await api.previewTask({
            asset_id: action.asset_id,
            task_type: action.task_type,
            waypoints: action.waypoints ?? [],
            channel: 'voice',
          })
        } catch (error) {
          // No checks, no approval: an order the world model could not look
          // at is not offered as one it did. The readback stays on screen so
          // the operator can drop it, and the map still takes direct orders.
          previewTrouble =
            error instanceof Refused && error.message ? error.message : say.assistant.noChecks
        }
      }
      setShowAllChecks(false)
      setProposal({ exchange, preview, previewTrouble })
      onProposal(preview?.path ?? null)
    },
    [onProposal],
  )

  const submit = useCallback(
    async (text: string, how: 'typed' | 'voice') => {
      const line = text.trim()
      if (!line || status === 'thinking') return
      setTrouble('')
      setDraft('')
      push({ who: 'you', text: line, at: Date.now() / 1000, how })
      setStatus('thinking')
      try {
        await took(await voice.say(token, line))
      } catch (error) {
        setTrouble(error instanceof Error ? error.message : say.assistant.unreachable)
      } finally {
        setStatus('idle')
      }
    },
    [status, token, took],
  )

  const begin = useCallback(async () => {
    if (!canHear || status !== 'idle') return
    setTrouble('')
    try {
      await ptt.current.start()
      setStatus('listening')
    } catch {
      setTrouble(say.voice.noMicrophone)
    }
  }, [canHear, status])

  const end = useCallback(async () => {
    if (status !== 'listening') return
    setStatus('thinking')
    try {
      const clip = await ptt.current.stop()
      if (!clip) return
      const exchange = await voice.listen(token, clip)
      // Printed before the reply, and kept there, so an operator can see
      // what the machine misheard when the answer is strange.
      push({ who: 'you', text: exchange.heard, at: Date.now() / 1000, how: 'voice' })
      await took(exchange)
    } catch (error) {
      setTrouble(error instanceof Error ? error.message : say.assistant.unreachable)
    } finally {
      setStatus('idle')
    }
  }, [status, token, took])

  // Space is the push-to-talk key, so it must not also scroll the page or
  // re-trigger on the operating system's key repeat. Never from a field.
  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.repeat) return
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'BUTTON'].includes(target.tagName)) return
      event.preventDefault()
      void begin()
    }
    const up = (event: KeyboardEvent) => {
      if (event.code !== 'Space') return
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'BUTTON'].includes(target.tagName)) return
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

  /** The readback answered. The only thing here that makes anything happen. */
  const answer = useCallback(
    async (confirmed: boolean) => {
      if (!proposal) return
      setProposal(null)
      onProposal(null)
      setStatus('thinking')
      try {
        const result = await voice.confirm(token, proposal.exchange.exchange_id, confirmed)
        push({ who: 'argus', text: result.spoken, at: Date.now() / 1000 })
        voice.play(result)
        if (confirmed) onOrdered?.()
      } catch (error) {
        setTrouble(error instanceof Error ? error.message : say.assistant.unreachable)
      } finally {
        setStatus('idle')
      }
    },
    [proposal, token, onProposal, onOrdered],
  )

  if (collapsed) {
    // Folded because the service cannot be reached: the rail says so, on
    // hover and to assistive technology, and still opens on a click.
    const railSays = reached === false ? say.assistant.unreachable : say.assistant.expand
    return (
      <aside className="assistant is-collapsed">
        <button className="assistant-expand" onClick={onToggle} title={railSays} aria-label={railSays}>
          <ArgusGlyph />
          {reached === false && <span className="dot is-off" aria-hidden />}
          {proposal && <span className="badge" aria-label={say.operate.awaitingYou} />}
        </button>
      </aside>
    )
  }

  const standing =
    capabilities === null
      ? say.voice.thinking
      : capabilities === 'unreached'
        ? say.assistant.unreachable
        : !capabilities.can_understand
          ? say.assistant.cannotUnderstand
          : ''

  return (
    <aside className="assistant card">
      <header className="assistant-head">
        <ArgusGlyph />
        <div className="assistant-title">
          <div>
            <span className="assistant-name">{say.assistant.name}</span>
            <span className="pill is-sel is-small">{say.assistant.badge}</span>
          </div>
          <span className="sub">{say.assistant.tagline}</span>
        </div>
        <button className="icon-button" onClick={onToggle} title={say.assistant.collapse} aria-label={say.assistant.collapse}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 6l6 6-6 6" />
          </svg>
        </button>
      </header>

      <div className="assistant-body" ref={scroller}>
        {standing && <p className="assistant-standing">{standing}</p>}
        {messages.map((message, i) => (
          <div key={i} className={`msg is-${message.who}`}>
            <p>{message.text}</p>
            <span className="msg-meta">
              {clockAt(message.at)} ·{' '}
              {message.who === 'you'
                ? `${say.assistant.you}, ${message.how === 'voice' ? say.assistant.byVoice : say.assistant.typed}`
                : say.assistant.name}
            </span>
          </div>
        ))}
        {proposal && (
          <ProposalCard
            proposal={proposal}
            showAll={showAllChecks}
            onShowAll={() => setShowAllChecks(true)}
            busy={status === 'thinking'}
            onApprove={() => void answer(true)}
            onDecline={() => void answer(false)}
          />
        )}
        {trouble && <p className="assistant-trouble">{trouble}</p>}
        {status === 'listening' && <p className="assistant-standing">{say.voice.listening}</p>}
        {status === 'thinking' && !proposal && <p className="assistant-standing">{say.voice.thinking}</p>}
      </div>

      {canUnderstand && messages.length === 0 && (
        <div className="suggestions">
          {say.assistant.suggestions.map((line) => (
            <button key={line} className="suggestion" onClick={() => void submit(line, 'typed')}>
              {line}
            </button>
          ))}
        </div>
      )}

      <form
        className="assistant-input"
        onSubmit={(event) => {
          event.preventDefault()
          void submit(draft, 'typed')
        }}
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={say.assistant.placeholder}
          disabled={!canUnderstand || status === 'thinking'}
          aria-label={say.assistant.send}
        />
        <button
          type="button"
          className={`ptt${status === 'listening' ? ' live' : ''}`}
          disabled={!canHear || status === 'thinking'}
          title={canHear ? say.voice.hold : say.voice.unavailable}
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
        <button type="submit" className="send" disabled={!canUnderstand || !draft.trim() || status === 'thinking'} aria-label={say.assistant.send}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h13M13 6l6 6-6 6" />
          </svg>
        </button>
      </form>
    </aside>
  )
}

/**
 * The proposal: what Argus would send, what the world model checked, and
 * the two buttons. The checks are the server's words with their sources;
 * nothing here is composed. The primary button is disabled while a check
 * has failed, and says nothing more certain than the checks do.
 */
function ProposalCard({
  proposal,
  showAll,
  onShowAll,
  busy,
  onApprove,
  onDecline,
}: {
  proposal: Proposal
  showAll: boolean
  onShowAll: () => void
  busy: boolean
  onApprove: () => void
  onDecline: () => void
}) {
  const { exchange, preview, previewTrouble } = proposal
  const action = exchange.action
  const checks = preview?.checks ?? []
  const passed = checks.filter((c) => c.state === 'pass').length
  const needYou = checks.filter((c) => c.state === 'needs_you').length
  const failed = checks.filter((c) => c.state === 'fail').length
  const shown = showAll ? checks : checks.filter((c) => c.state !== 'pass')
  // A distance the server could not measure is said to be unknown, never 0.
  const facts = preview
    ? [
        preview.distance_m === null ? say.assistant.noDistance : say.assistant.distance(preview.distance_m),
        preview.eta_sec === null ? say.assistant.noEta : say.assistant.eta(preview.eta_sec),
        say.assistant.stops(preview.waypoints.length),
      ].join(' · ')
    : previewTrouble

  return (
    <section className="proposal card" aria-label={say.operate.awaitingYou}>
      <header>
        <div>
          <strong>
            {action ? `${plain(action.task_type)}${action.place ? ` · ${action.place}` : ''}` : exchange.heard}
          </strong>
          <span className="sub">{action?.machine ? `${action.machine} · ${facts}` : facts}</span>
        </div>
        <span className="pill is-warn is-small">{say.operate.awaitingYou}</span>
      </header>
      {checks.length > 0 && (
        <div className="checks">
          <div className="checks-summary">
            {passed > 0 && <span className="pill is-ok is-small">{say.assistant.checksPassed(passed)}</span>}
            {needYou > 0 && <span className="pill is-warn is-small">{say.assistant.needYou(needYou)}</span>}
            {failed > 0 && <span className="pill is-act is-small">{say.assistant.blocked(failed)}</span>}
            {!showAll && shown.length < checks.length && (
              <button className="link" onClick={onShowAll}>
                {say.assistant.showAll}
              </button>
            )}
          </div>
          {shown.map((check) => (
            <div key={check.id} className={`check is-${checkStatus(check.state)}`}>
              <span className="ico" aria-hidden />
              <div>
                <span>{check.text}</span>
                <span className="check-source">{check.source}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <footer>
        <button className="btn" onClick={onDecline} disabled={busy}>
          {say.assistant.decline}
        </button>
        <button className="btn primary" onClick={onApprove} disabled={busy || preview === null || !preview.can_send}>
          {say.assistant.approve}
        </button>
      </footer>
    </section>
  )
}

/** pass is healthy, needs_you is attention, fail is act; anything else attention. */
function checkStatus(state: string): 'ok' | 'warn' | 'act' {
  if (state === 'pass') return 'ok'
  if (state === 'fail') return 'act'
  return 'warn'
}

function ArgusGlyph() {
  return (
    <span className="argus-glyph" aria-hidden>
      <ArgusIcon className="argus-glyph-mark" />
    </span>
  )
}
