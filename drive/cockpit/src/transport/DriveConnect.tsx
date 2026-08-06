import { useEffect, useRef, useState } from 'react'
import type { RemoLink } from './useRemoTransport'

/**
 * The entire entry experience for someone you share the link with:
 *   open link → enter password → (auto) connect → (auto) 5s live check →
 *   "Ready" → cockpit. No extra buttons, no setup on their end.
 *
 * The 5s check runs the link for a full window and only declares ready if it
 * stays connected with a granted role. A bad password fails fast.
 */
type Phase =
  | 'password'
  | 'checking'
  | 'ready-driver'
  | 'ready-spectator'
  | 'fail-auth'
  | 'fail-link'
const CHECK_MS = 5000

export function DriveConnect({
  link,
  hasPassword,
  onSetPassword,
  onClearPassword,
  onEnter,
}: {
  link: RemoLink
  hasPassword: boolean
  onSetPassword: (pw: string) => void
  onClearPassword: () => void
  onEnter: () => void
}) {
  const [phase, setPhase] = useState<Phase>(hasPassword ? 'checking' : 'password')
  const [pw, setPw] = useState('')
  const [remain, setRemain] = useState(Math.ceil(CHECK_MS / 1000))
  const timers = useRef<ReturnType<typeof setInterval>[]>([])
  const linkRef = useRef(link)
  useEffect(() => {
    linkRef.current = link
  }, [link])

  const clearTimers = () => {
    timers.current.forEach(clearInterval)
    timers.current.forEach(clearTimeout)
    timers.current = []
  }
  useEffect(() => () => clearTimers(), [])

  // lock the page behind the modal
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])

  // settle() may run from a timer callback — setState here is fine (not in an effect)
  const settle = (p: Phase) => {
    clearTimers()
    setPhase(p)
    if (p === 'fail-auth') onClearPassword()
    if (p === 'ready-driver') {
      const t = setTimeout(onEnter, 1300) // show "Ready" briefly, then drop into the cockpit
      timers.current = [t]
    }
  }

  // create the 5s poll loop (no synchronous setState — safe to call from an effect)
  const beginPoll = () => {
    const started = Date.now()
    const poll = setInterval(() => {
      const left = Math.max(0, CHECK_MS - (Date.now() - started))
      setRemain(Math.ceil(left / 1000))
      const l = linkRef.current
      if (l.authFailed) {
        settle('fail-auth')
        return
      }
      if (left <= 0) {
        if (l.status === 'open' && l.role)
          settle(l.role === 'DRIVER' ? 'ready-driver' : 'ready-spectator')
        else settle('fail-link')
      }
    }, 200)
    timers.current = [poll]
  }

  // returning visitor already has the password → start the check immediately
  useEffect(() => {
    if (hasPassword) beginPoll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submitPassword = (e: React.FormEvent) => {
    e.preventDefault()
    if (!pw.trim()) return
    onSetPassword(pw.trim())
    setRemain(Math.ceil(CHECK_MS / 1000))
    setPhase('checking')
    beginPoll()
  }

  const retry = () => {
    setRemain(Math.ceil(CHECK_MS / 1000))
    setPhase('checking')
    beginPoll()
  }

  const reenter = () => {
    clearTimers()
    setPw('')
    setPhase('password')
  }

  const pct = 100 - (remain / (CHECK_MS / 1000)) * 100

  return (
    <div className="fixed inset-0 z-[2000] grid select-none place-items-center bg-bg p-6">
      <div className="w-full max-w-[360px] rounded-card border border-line-strong bg-surface-2 p-6 shadow-overlay">
        <div className="mb-1 text-[15px] font-semibold text-text">ARGUS · Drive access</div>

        {phase === 'password' && (
          <form onSubmit={submitPassword}>
            <p className="mb-4 text-[13px] leading-5 text-text-3">
              This cockpit controls a real vehicle. Enter the access password to connect.
            </p>
            <input
              type="password"
              autoFocus
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="Password"
              className="mb-3 w-full rounded-control border border-line bg-surface-inset px-3 py-2 font-mono text-[14px] text-text outline-none focus:border-accent"
            />
            <button
              type="submit"
              disabled={!pw.trim()}
              className="w-full rounded-control bg-accent px-4 py-2 text-[14px] font-bold text-white transition-opacity disabled:opacity-40"
            >
              Connect
            </button>
          </form>
        )}

        {phase === 'checking' && (
          <div>
            <p className="mb-4 text-[13px] leading-5 text-text-3">
              Connecting and verifying the link is live… {remain}s
            </p>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-inset">
              <div className="h-full rounded-full bg-accent transition-[width] duration-200" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {phase === 'ready-driver' && (
          <ResultBlock tone="success" title="Ready to drive" sub="Link verified. Taking you to the cockpit…" />
        )}

        {phase === 'ready-spectator' && (
          <div>
            <ResultBlock tone="warning" title="Connected — viewer" sub="Someone else is driving right now. You can watch; controls activate when they leave." />
            <button type="button" onClick={onEnter} className="mt-4 w-full rounded-control bg-accent px-4 py-2 text-[14px] font-bold text-white">
              Watch
            </button>
          </div>
        )}

        {phase === 'fail-auth' && (
          <div>
            <ResultBlock tone="critical" title="Wrong password" sub="The vehicle rejected that password." />
            <button type="button" onClick={reenter} className="mt-4 w-full rounded-control bg-accent px-4 py-2 text-[14px] font-bold text-white">
              Try again
            </button>
          </div>
        )}

        {phase === 'fail-link' && (
          <div>
            <ResultBlock tone="critical" title="No link" sub="Couldn't reach the vehicle. It may be offline — try again in a moment." />
            <div className="mt-4 flex gap-2">
              <button type="button" onClick={retry} className="flex-1 rounded-control bg-accent px-4 py-2 text-[14px] font-bold text-white">
                Retry
              </button>
              <button type="button" onClick={reenter} className="rounded-control px-3 py-2 text-[13px] text-text-3 hover:text-text-2">
                Change
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ResultBlock({ tone, title, sub }: { tone: 'success' | 'warning' | 'critical'; title: string; sub: string }) {
  const dot = tone === 'success' ? 'bg-success' : tone === 'warning' ? 'bg-warning' : 'bg-critical'
  const text = tone === 'success' ? 'text-success' : tone === 'warning' ? 'text-warning' : 'text-critical'
  return (
    <div className="rounded-control border border-line bg-surface-inset px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        <span className={`text-[13px] font-semibold ${text}`}>{title}</span>
      </div>
      <p className="mt-1 pl-4 text-[12px] leading-4 text-text-3">{sub}</p>
    </div>
  )
}
