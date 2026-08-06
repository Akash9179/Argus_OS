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
import type { ReactNode } from 'react'
import { say } from './wording'

export type ShellApp = 'desktop' | 'operate' | 'drive'

const DRIVE_URL_KEY = 'argus.driveUrl'
export function driveUrl(): string {
  return (
    window.localStorage.getItem(DRIVE_URL_KEY) ??
    'http://localhost:5174/?bridge=localhost:8090'
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
        <g stroke="var(--wall-line)" strokeWidth="1.2" fill="none">
          <path d="M-50,700 Q300,640 640,700 T1650,660" />
          <path d="M-50,760 Q300,700 640,760 T1650,720" />
          <path d="M-50,820 Q300,762 640,822 T1650,782" />
          <path d="M-50,880 Q300,824 640,884 T1650,844" />
          <path d="M-50,300 Q380,230 760,300 T1650,250" />
          <path d="M-50,240 Q380,170 760,240 T1650,190" />
        </g>
        <path d="M-50,470 Q400,540 820,455 T1650,500" stroke="var(--wall-road)" strokeWidth="46" fill="none" opacity="0.85" />
        <g stroke="var(--wall-grid)" strokeWidth="1">
          <line x1="0" y1="200" x2="1600" y2="200" />
          <line x1="0" y1="400" x2="1600" y2="400" />
          <line x1="0" y1="600" x2="1600" y2="600" />
          <line x1="0" y1="800" x2="1600" y2="800" />
          <line x1="266" y1="0" x2="266" y2="1000" />
          <line x1="533" y1="0" x2="533" y2="1000" />
          <line x1="800" y1="0" x2="800" y2="1000" />
          <line x1="1066" y1="0" x2="1066" y2="1000" />
          <line x1="1333" y1="0" x2="1333" y2="1000" />
        </g>
        <rect width="1600" height="1000" fill="url(#wp-ember)" />
      </svg>
    </div>
  )
}

/* ------------------------------- desktop ------------------------------- */

export function Desktop({ nowSec, line, healthy, open }: { nowSec: number; line: string; healthy: boolean; open: boolean }) {
  const d = new Date(nowSec * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const date = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
  return (
    <div className={`desktop${open ? '' : ' is-away'}`} aria-hidden={!open}>
      <div className="glance-time">
        {hh}:{mm}
      </div>
      <div className="glance-date">{date}</div>
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
  name: string
  live: boolean
  tip: string
  icon: ReactNode
}

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8 } as const

const DOCK: DockEntry[] = [
  {
    id: 'operate',
    name: say.shell.apps.operate,
    live: true,
    tip: say.shell.tips.operate,
    icon: (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M12 21s7-6.3 7-11a7 7 0 1 0-14 0c0 4.7 7 11 7 11z" />
        <circle cx="12" cy="10" r="2.5" />
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
        <circle cx="12" cy="12" r="8.5" />
        <circle cx="12" cy="12" r="2.4" />
        <path d="M12 14.4V20.5M9.8 10.9 4 8.6M14.2 10.9 20 8.6" />
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
        <circle cx="11" cy="11" r="6.5" />
        <path d="M16 16l4.5 4.5" />
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
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 7v5l3.5 2" />
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
        <rect x="3.5" y="13" width="7" height="7" rx="1.5" />
        <rect x="13.5" y="13" width="7" height="7" rx="1.5" />
        <rect x="8.5" y="3.5" width="7" height="7" rx="1.5" />
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
          <button
            key={entry.id}
            type="button"
            className={`dock-app${entry.live ? '' : ' is-disabled'}${active === entry.id ? ' is-running' : ''}`}
            onClick={() => entry.live && onOpen(entry.id as ShellApp)}
            aria-disabled={!entry.live}
          >
            <span className="tip">{entry.tip}</span>
            <span className="icon">{entry.icon}</span>
            <span className="dock-name">{entry.name}</span>
            <span className="running-dot" />
          </button>
        ))}
      </div>
    </>
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
