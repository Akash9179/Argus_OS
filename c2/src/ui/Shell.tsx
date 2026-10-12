/**
 * The operating-system shell: desktop, dock, and the application layer.
 *
 * The dock offers only the applications that exist: Operate, Drive and
 * Settings (founder decision, 12 Oct 2026). Names are always shown; an
 * operator should never have to know what a symbol means.
 *
 * Drive is today its own dev application (drive/cockpit). The shell hosts
 * it full-bleed through an iframe: the documented microfrontend seam until
 * the cockpit folds into this SDK application. Its address is in driveUrl.ts.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { clockDate, clockTime, setClockPrefs, useClockPrefs, zoneChoices } from './clockPrefs'
import { driveUrl, holdDriveFrame, isDriveEscape, postDriveActive } from './driveUrl'
import { say } from './wording'

export type ShellApp = 'desktop' | 'operate' | 'drive' | 'settings'

/* ------------------------------ wallpaper ------------------------------ */
/* The site itself, drawn: sky, terrain contours, the road, the survey grid.
   Colour washes are quiet on purpose; this is scenery, not signal. */

export function Wallpaper() {
  return (
    <div className="wallpaper" aria-hidden>
      <svg viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="wp-sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--wall-top)" />
            <stop offset="100%" stopColor="var(--wall-bottom)" />
          </linearGradient>
          <radialGradient id="wp-aurora" cx="72%" cy="12%" r="70%">
            <stop offset="0%" stopColor="var(--wall-glow-a)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
          <radialGradient id="wp-teal" cx="12%" cy="55%" r="60%">
            <stop offset="0%" stopColor="var(--wall-glow-b)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
          <radialGradient id="wp-ember" cx="50%" cy="96%" r="55%">
            <stop offset="0%" stopColor="var(--wall-glow-c)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>
        <rect width="1600" height="1000" fill="url(#wp-sky)" />
        <rect width="1600" height="1000" fill="url(#wp-aurora)" />
        <rect width="1600" height="1000" fill="url(#wp-teal)" />
        <g stroke="var(--wall-line)" strokeWidth="1.4" fill="none" opacity="0.9">
          <path d="M-50,700 Q300,640 640,700 T1650,660" />
          <path d="M-50,760 Q300,700 640,760 T1650,720" />
          <path d="M-50,820 Q300,762 640,822 T1650,782" />
          <path d="M-50,880 Q300,824 640,884 T1650,844" />
          <path d="M-50,300 Q380,230 760,300 T1650,250" />
          <path d="M-50,240 Q380,170 760,240 T1650,190" />
        </g>
        <path d="M-50,470 Q400,540 820,455 T1650,500" stroke="var(--wall-road)" strokeWidth="46" fill="none" opacity="0.85" />
        <rect width="1600" height="1000" fill="url(#wp-ember)" />
      </svg>
    </div>
  )
}

/* ------------------------------- desktop ------------------------------- */

export function Desktop({ nowSec, line, healthy, open }: { nowSec: number; line: string; healthy: boolean; open: boolean }) {
  const prefs = useClockPrefs()
  return (
    <div className={`desktop${open ? '' : ' is-away'}`} aria-hidden={!open}>
      <div className="glance-time">{clockTime(nowSec, prefs)}</div>
      <div className="glance-date">{clockDate(nowSec, prefs)}</div>
      <div className="glance-state">
        <span className={`dot ${healthy ? 'is-ok' : 'is-warn'}`} />
        <span>{line}</span>
      </div>
    </div>
  )
}

/* --------------------------------- dock --------------------------------- */

interface DockEntry {
  id: ShellApp
  sep?: boolean
  name: string
  tip: string
  icon: ReactNode
}

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 2 } as const

const DOCK: DockEntry[] = [
  {
    id: 'operate',
    name: say.shell.apps.operate,
    tip: say.shell.tips.operate,
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M3.5 19c3-6 5-2.5 8-7s5.5-5 9-6" strokeDasharray="2.6 2.2" opacity="0.75" strokeWidth="1.6" />
        <path d="M12 20s5.4-4.9 5.4-8.5A5.4 5.4 0 1 0 6.6 11.5C6.6 15.1 12 20 12 20z" fill="rgba(255,255,255,0.14)" />
        <circle cx="12" cy="11.3" r="2" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
  {
    id: 'drive',
    name: say.shell.apps.drive,
    tip: say.shell.tips.drive,
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <circle cx="12" cy="12" r="8.6" fill="rgba(255,255,255,0.08)" />
        <circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none" />
        <path d="M12 14.6V20.4M9.6 11 3.8 9M14.4 11 20.2 9" strokeWidth="2.4" />
      </svg>
    ),
  },
  {
    id: 'settings',
    name: say.shell.settings.title,
    tip: say.shell.tips.settings,
    sep: true,
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <circle cx="12" cy="12" r="7.4" fill="rgba(255,255,255,0.08)" strokeWidth="2.6" strokeDasharray="2.7 2.4" />
        <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
]

export function Dock({ active, away, onOpen }: { active: ShellApp; away: boolean; onOpen: (app: ShellApp) => void }) {
  // While an application is open the dock is put away entirely (no hover
  // strip to bring it back): at 1280 wide it used to cover Drive's control
  // bar. The top bar's tabs, the ARGUS mark and Esc all return to the
  // desktop, so nothing is lost.
  return (
    <>
      <div className={`dock${away ? ' is-away' : ''}`} aria-hidden={away}>
        {DOCK.map((entry) => (
          <span key={entry.id} style={{ display: 'contents' }}>
          {entry.sep && <span className="dock-sep" aria-hidden />}
          <button
            type="button"
            className={`dock-app${active === entry.id ? ' is-running' : ''}`}
            onClick={() => onOpen(entry.id)}
          >
            <span className="tip">{entry.tip}</span>
            <span className={`icon i-${entry.id}`}>{entry.icon}</span>
            <span className="dock-name">{entry.name}</span>
            <span className="running-dot" />
          </button>
          </span>
        ))}
      </div>
    </>
  )
}

/* ----------------------------- settings app ----------------------------- */

type Theme = 'dark' | 'day'

export function SettingsApp({ open, theme, onTheme, onClose }: { open: boolean; theme: Theme; onTheme: (t: Theme) => void; onClose: () => void }) {
  const nav = say.shell.settings.nav
  const ap = say.shell.settings.appearance
  const tm = say.shell.settings.time
  const [pane, setPane] = useState<'appearance' | 'time'>('appearance')
  const prefs = useClockPrefs()
  return (
    <div className={`shell-app is-settings${open ? '' : ' is-away'}`} aria-hidden={!open}>
      <div className="swindow">
        <div className="swin-bar">
          <button type="button" className="swin-close" onClick={onClose} title={say.shell.settings.closeHint} aria-label={say.shell.settings.close} />
          <span className="swin-bar-title">{say.shell.settings.title}</span>
        </div>
        <div className="swin-side">
          <div className="swin-title">{say.shell.settings.title.toUpperCase()}</div>
          <button type="button" className={`snav as-nav${pane === 'appearance' ? ' is-active' : ''}`} onClick={() => setPane('appearance')}>{nav.appearance}</button>
          <button type="button" className={`snav as-nav${pane === 'time' ? ' is-active' : ''}`} onClick={() => setPane('time')}>{nav.time}</button>
        </div>
        {pane === 'time' ? (
        <div className="swin-main">
          <h2>{tm.heading}</h2>
          <p className="swin-sub">{tm.sub}</p>
          <div className="sfield">
            <label htmlFor="tz-select">{tm.zone}</label>
            <select id="tz-select" value={prefs.timeZone} onChange={(e) => setClockPrefs({ timeZone: e.target.value })}>
              <option value="">{tm.zoneSystem}</option>
              <option value="UTC">{tm.zoneUtc}</option>
              <option disabled>{'\u2014\u2014\u2014\u2014\u2014\u2014'}</option>
              {zoneChoices().map((z) => (
                <option key={z} value={z}>{z.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div className="sfield">
            <span>{tm.format}</span>
            <div className="swatches">
              <button type="button" className={`swatch is-mini${!prefs.twelveHour ? ' is-on' : ''}`} onClick={() => setClockPrefs({ twelveHour: false })}>
                <span className="swatch-label">{tm.h24}<small>{tm.h24Note}</small></span>
              </button>
              <button type="button" className={`swatch is-mini${prefs.twelveHour ? ' is-on' : ''}`} onClick={() => setClockPrefs({ twelveHour: true })}>
                <span className="swatch-label">{tm.h12}<small>{tm.h12Note}</small></span>
              </button>
            </div>
          </div>
        </div>
        ) : (
        <div className="swin-main">
          <h2>{ap.heading}</h2>
          <p className="swin-sub">{ap.sub}</p>
          <div className="swatches">
            <button type="button" className={`swatch${theme === 'dark' ? ' is-on' : ''}`} onClick={() => onTheme('dark')}>
              <svg className="swatch-art" viewBox="0 0 200 62" preserveAspectRatio="none">
                <rect width="200" height="62" fill="#0a0d10" /><rect width="200" height="9" fill="#171b1f" />
                <rect x="12" y="20" width="58" height="30" rx="4" fill="#20252a" /><rect x="78" y="20" width="110" height="30" rx="4" fill="#161a1e" />
                <circle cx="150" cy="35" r="4" fill="#30d158" />
              </svg>
              <span className="swatch-label">{ap.dark}<small>{ap.darkNote}</small></span>
            </button>
            <button type="button" className={`swatch${theme === 'day' ? ' is-on' : ''}`} onClick={() => onTheme('day')}>
              <svg className="swatch-art" viewBox="0 0 200 62" preserveAspectRatio="none">
                <rect width="200" height="62" fill="#e6eaef" /><rect width="200" height="9" fill="#fafbfc" />
                <rect x="12" y="20" width="58" height="30" rx="4" fill="#ffffff" /><rect x="78" y="20" width="110" height="30" rx="4" fill="#f0f3f6" />
                <circle cx="150" cy="35" r="4" fill="#248a3d" />
              </svg>
              <span className="swatch-label">{ap.day}<small>{ap.dayNote}</small></span>
            </button>
          </div>
        </div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------ drive app ------------------------------ */

export function DriveApp({ open, onEscape }: { open: boolean; onEscape: () => void }) {
  // The frame stays mounted while the operator is elsewhere, so it is told
  // on every change whether Drive is the active screen, and again whenever
  // it loads. Leaving Drive relinquishes control (founder decision, 12 Oct
  // 2026); the cockpit drops the arm and stops commanding.
  const frame = useRef<HTMLIFrameElement>(null)
  const openRef = useRef(open)
  useEffect(() => {
    openRef.current = open
    postDriveActive(frame.current, open)
  }, [open])
  // Esc inside the cockpit stays in the cockpit's window. The cockpit posts
  // an escape request instead, believed only from this frame and origin.
  const onEscapeRef = useRef(onEscape)
  useEffect(() => {
    onEscapeRef.current = onEscape
  }, [onEscape])
  // Signing out (by hand, or by a refused token) tells the cockpit first:
  // Drive is no longer active, then the session is over. The station keeps
  // this frame mounted until the cockpit answers (signOutDrive), so it is
  // named where the sign-out can find it.
  useEffect(() => holdDriveFrame(frame.current), [])
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (isDriveEscape(event, frame.current)) onEscapeRef.current()
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])
  return (
    <div className={`shell-app${open ? '' : ' is-away'}`} aria-hidden={!open}>
      <iframe
        ref={frame}
        className="drive-frame"
        src={driveUrl()}
        title={say.shell.apps.drive}
        allow="camera; microphone; gamepad"
        onLoad={() => postDriveActive(frame.current, openRef.current)}
      />
    </div>
  )
}
