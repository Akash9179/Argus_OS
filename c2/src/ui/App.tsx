/**
 * The application shell.
 *
 * The menu bar belongs to the operating system and is identical in every
 * application. Only Operate exists in this build; the rest of the launcher
 * is visible and plainly disabled, because hiding it would misrepresent
 * what the system is.
 */

import { useEffect, useState } from 'react'
import { saveToken, savedToken, track as api } from '../sdk/client'
import { onSignedOut, signOut } from '../sdk/session'
import { isAnswering, useWorld } from '../state/world'
import { Operate } from './Operate'
import { Desktop, Dock, DriveApp, SettingsApp, Wallpaper, type ShellApp } from './Shell'
import { say } from './wording'
import { clockDate, clockTime, useClockPrefs, zoneLabel } from './clockPrefs'

type Theme = 'dark' | 'day'

export function App() {
  const [signedIn, setSignedIn] = useState(() => savedToken() !== '')
  const [theme, setTheme] = useState<Theme>('dark')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  // A token refused by any interface ends the session here, so a revoked
  // key shows sign-in rather than a station that has apparently lost the
  // site.
  useEffect(() => onSignedOut(() => setSignedIn(false)), [])

  if (!signedIn) return <SignIn onSignedIn={() => setSignedIn(true)} />
  return <Station theme={theme} onTheme={setTheme} onSignOut={signOut} />
}

function Station({
  theme,
  onTheme,
  onSignOut,
}: {
  theme: Theme
  onTheme: (t: Theme) => void
  onSignOut: () => void
}) {
  const { world, link, ready } = useWorld()
  // The same silence test the rails use, so the menu bar can never claim a
  // machine is answering while its row reads "No answer".
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const answeringCount = [...world.assets.keys()].filter((id) =>
    isAnswering(world, id, now, link === 'lost'),
  ).length

  // Who is signed in, in the name the server resolves. C2 holds a token and
  // nothing else, so this is the only way to put a person on screen without
  // showing the identifier underneath them.
  const [who, setWho] = useState('')
  const clockPrefs = useClockPrefs()

  // The shell: which application is up. The desktop is the resting state,
  // and Esc always brings it back (never from inside a text field).
  const [screen, setScreen] = useState<ShellApp>('desktop')
  const [driveOpened, setDriveOpened] = useState(false)
  const openApp = (app: ShellApp) => {
    setScreen(app)
    if (app === 'drive') setDriveOpened(true)
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return
      if (e.key === 'Escape') setScreen('desktop')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => {
    let cancelled = false
    void api
      .me()
      .then((principal) => {
        if (!cancelled) setWho(principal.display_name)
      })
      // Not knowing who is signed in is not worth an error on an operator's
      // screen. The name is simply left out.
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const glanceLine =
    link === 'lost' ? say.shell.glance.linkDown : say.shell.glance.allQuiet(answeringCount)

  return (
    <div className="station">
      <header className="topbar">
        <button className="mark as-button" onClick={() => setScreen('desktop')} title={say.shell.desktop}>
          <span className="mark-name">ARGUS</span>
          <span className="mark-sub">{say.shell.station}</span>
        </button>
        <nav className="tabs" aria-label={say.shell.launcher}>
          <button className={`tab${screen === 'operate' ? ' on' : ''}`} onClick={() => openApp('operate')}>
            {say.shell.apps.operate}
          </button>
          <button className={`tab${screen === 'drive' ? ' on' : ''}`} onClick={() => openApp('drive')}>
            {say.shell.apps.drive}
          </button>
          {[say.shell.apps.review, say.shell.apps.intel, say.shell.apps.fleet].map((name) => (
            <span key={name} className="tab soon" title={say.notBuiltYet}>
              {name}
            </span>
          ))}
        </nav>
        <div className="topbar-right">
          <span className={`pill is-${link === 'good' ? 'ok' : link === 'lost' ? 'act' : 'warn'}`}>
            <span className="dot" />
            {link === 'good' ? say.link.good : link === 'lost' ? say.link.lost : say.link.connecting}
            {link === 'good' && ` · ${say.counts.answering(answeringCount, world.assets.size)}`}
          </span>
          <span className="clock">
            {clockDate(now, clockPrefs)}&nbsp;&nbsp;{clockTime(now, clockPrefs)} {zoneLabel(now, clockPrefs)}
          </span>
          <button className="who as-button" onClick={() => openApp('settings')} title={say.shell.tips.settings}>
            <span className="avatar" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="8.5" r="3.6" />
                <path d="M5 19.5c1.4-3.2 4-4.6 7-4.6s5.6 1.4 7 4.6" />
              </svg>
            </span>
            {who && <span className="who-name">{who}</span>}
          </button>
          <button className="chip" onClick={onSignOut}>
            {say.signOut}
          </button>
        </div>
      </header>

      <div className="shell-stage">
        <Wallpaper />
        <Desktop nowSec={now} line={glanceLine} healthy={link !== 'lost'} open={screen === 'desktop'} />
        <div className={`shell-app${screen === 'operate' ? '' : ' is-away'}`} aria-hidden={screen !== 'operate'}>
          {ready ? (
            <Operate world={world} link={link} theme={theme} />
          ) : (
            <div className="waiting">{say.link.connecting}</div>
          )}
        </div>
        {driveOpened && <DriveApp open={screen === 'drive'} />}
        <SettingsApp open={screen === 'settings'} theme={theme} onTheme={onTheme} onClose={() => setScreen('desktop')} />
        <Dock active={screen} away={screen !== 'desktop'} onOpen={openApp} />
      </div>
    </div>
  )
}

function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [key, setKey] = useState('')
  const [problem, setProblem] = useState('')
  const [checking, setChecking] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setChecking(true)
    setProblem('')
    try {
      if (await api.checkToken(key.trim())) {
        saveToken(key.trim())
        onSignedIn()
      } else {
        setProblem(say.signIn.refused)
      }
    } catch {
      setProblem(say.signIn.unreachable)
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="signin">
      <form onSubmit={submit}>
        <span className="mark">ARGUS</span>
        <h1>{say.signIn.title}</h1>
        <p>{say.signIn.prompt}</p>
        <label>
          {say.signIn.field}
          <input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            type="password"
            autoFocus
            spellCheck={false}
          />
        </label>
        {problem && <p className="problem">{problem}</p>}
        <button className="primary" disabled={checking || key.trim() === ''}>
          {say.signIn.action}
        </button>
      </form>
    </div>
  )
}
