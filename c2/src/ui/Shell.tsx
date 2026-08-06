/**
 * The operating-system shell: desktop, dock, and the application layer.
 *
 * The dock is the honest launcher: applications that exist are live, and
 * applications that do not are visible and plainly disabled, because hiding
 * them would misrepresent what the system is. Names are always shown; an
 * operator should never have to know what a symbol means.
 *
 * Drive is today its own dev application (drive/cockpit). The shell hosts
 * it full-bleed through an iframe: the documented microfrontend seam until
 * the cockpit folds into this SDK application. Override the address with
 * localStorage 'argus.driveUrl'; the default matches the local dev pair.
 */
import { useState, type ReactNode } from 'react'
import { clockDate, clockTime, setClockPrefs, useClockPrefs, zoneChoices } from './clockPrefs'
import { say } from './wording'

export type ShellApp = 'desktop' | 'operate' | 'drive' | 'settings'

const DRIVE_URL_KEY = 'argus.driveUrl'
export function driveUrl(): string {
  return (
    window.localStorage.getItem(DRIVE_URL_KEY) ??
    (import.meta.env.VITE_DRIVE_URL as string | undefined) ??
    'http://localhost:5174/?bridge=localhost:8090&key=Argus@2026'
  )
}

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
  id: ShellApp | 'intel' | 'review' | 'fleet'
  sep?: boolean
  name: string
  live: boolean
  tip: string
  icon: ReactNode
}

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 2 } as const

const DOCK: DockEntry[] = [
  {
    id: 'operate',
    name: say.shell.apps.operate,
    live: true,
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
    live: true,
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
    id: 'intel',
    name: say.shell.apps.intel,
    live: false,
    tip: say.notBuiltYet,
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <circle cx="12" cy="12" r="8.6" opacity="0.9" />
        <path d="M12 12 L18.6 7.6 A8.6 8.6 0 0 0 12 3.4 Z" fill="rgba(255,255,255,0.22)" stroke="none" />
        <circle cx="8.6" cy="14.2" r="1.3" fill="currentColor" stroke="none" />
        <circle cx="15" cy="15.6" r="1" fill="currentColor" stroke="none" opacity="0.7" />
      </svg>
    ),
  },
  {
    id: 'review',
    name: say.shell.apps.review,
    live: false,
    tip: say.notBuiltYet,
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <circle cx="12" cy="12" r="8.6" fill="rgba(255,255,255,0.08)" />
        <path d="M12 6.8V12l3.6 2.1" strokeWidth="2.4" />
        <path d="M5.5 3.8 3 6.3M18.5 3.8 21 6.3" strokeWidth="1.6" opacity="0.8" />
      </svg>
    ),
  },
  {
    id: 'fleet',
    name: say.shell.apps.fleet,
    live: false,
    tip: say.notBuiltYet,
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <rect x="8.4" y="3.4" width="7.2" height="7.2" rx="2" fill="rgba(255,255,255,0.2)" stroke="none" />
        <rect x="3" y="13.4" width="7.2" height="7.2" rx="2" fill="rgba(255,255,255,0.12)" stroke="none" />
        <rect x="13.8" y="13.4" width="7.2" height="7.2" rx="2" fill="rgba(255,255,255,0.12)" stroke="none" />
        <path d="M12 10.6v1.6M12 12.2l-5 1.2M12 12.2l5 1.2" strokeWidth="1.4" opacity="0.8" />
      </svg>
    ),
  },
  {
    id: 'settings',
    name: say.shell.settings.title,
    live: true,
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
  return (
    <>
      {/* hot strip: brushing the bottom edge brings the dock back while an app is open */}
      {away && <div className="dock-reveal" aria-hidden />}
      <div className={`dock${away ? ' is-away' : ''}`}>
        {DOCK.map((entry) => (
          <span key={entry.id} style={{ display: 'contents' }}>
          {entry.sep && <span className="dock-sep" aria-hidden />}
          <button
            type="button"
            className={`dock-app${entry.live ? '' : ' is-disabled'}${active === entry.id ? ' is-running' : ''}`}
            onClick={() => entry.live && onOpen(entry.id as ShellApp)}
            aria-disabled={!entry.live}
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
          <button type="button" className="swin-close" onClick={onClose} title="Close (Esc)" aria-label="Close settings" />
          <span className="swin-bar-title">{say.shell.settings.title}</span>
        </div>
        <div className="swin-side">
          <div className="swin-title">{say.shell.settings.title.toUpperCase()}</div>
          {([nav.zones, nav.machines, nav.people] as string[]).map((label) => (
            <div key={label} className="snav is-inert" title={say.notBuiltYet}>{label}</div>
          ))}
          <button type="button" className={`snav as-nav${pane === 'appearance' ? ' is-active' : ''}`} onClick={() => setPane('appearance')}>{nav.appearance}</button>
          <button type="button" className={`snav as-nav${pane === 'time' ? ' is-active' : ''}`} onClick={() => setPane('time')}>{nav.time}</button>
          <div className="snav is-inert" title={say.notBuiltYet}>{nav.ai}</div>
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

export function DriveApp({ open }: { open: boolean }) {
  return (
    <div className={`shell-app${open ? '' : ' is-away'}`} aria-hidden={!open}>
      <iframe className="drive-frame" src={driveUrl()} title={say.shell.apps.drive} allow="camera; microphone; gamepad" />
    </div>
  )
}
