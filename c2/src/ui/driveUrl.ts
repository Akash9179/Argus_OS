/**
 * Where the Drive cockpit lives, and how C2 talks to its frame.
 *
 * Drive is its own dev application (drive/cockpit), hosted in an iframe.
 * The address comes from localStorage 'argus.driveUrl', then from
 * VITE_DRIVE_URL (c2/.env.local, never committed), then the default below.
 *
 * Configuration holds the address only. Vite inlines every VITE_ variable
 * into the client bundle, so a bridge key written there would ship to
 * anyone holding the build. vite.config.ts drops any `key` query
 * parameter before the build writes the value, driveUrl() drops one again
 * from whatever it reads at run time, and the cockpit asks for the key.
 */

import { withoutKey } from './driveAddress'

export const DRIVE_URL_KEY = 'argus.driveUrl'

let warnedAboutKey = false

export function driveUrl(): string {
  const configured =
    window.localStorage.getItem(DRIVE_URL_KEY) ??
    (import.meta.env.VITE_DRIVE_URL as string | undefined) ??
    'http://localhost:5174/?bridge=localhost:8090'
  const { url, hadKey } = withoutKey(configured)
  if (hadKey && !warnedAboutKey) {
    warnedAboutKey = true
    // A developer message for the console, not an operator-facing string.
    console.warn('ARGUS: the Drive address carried a bridge key. It was ignored; the cockpit asks for the key itself.')
  }
  return url
}

/** The cockpit's origin: the only target C2 posts to. Never '*'. */
export function driveOrigin(): string {
  return new URL(driveUrl(), window.location.href).origin
}

/**
 * Tells the cockpit whether Drive is the active screen. Founder decision,
 * 12 Oct 2026: leaving Drive relinquishes control. The cockpit drops the
 * arm and stops commanding until the operator returns and arms again.
 */
export const DRIVE_ACTIVE = 'argus.drive.active'

export interface DriveActiveMessage {
  type: typeof DRIVE_ACTIVE
  active: boolean
}

/**
 * The cockpit's request to return to the desktop. Esc pressed inside the
 * frame never reaches C2's own window, so the cockpit posts this instead.
 */
export const DRIVE_ESCAPE = 'argus.drive.escape'

/**
 * True only for an escape request from this frame's own window and the
 * cockpit's origin. Any other page could post the same shape.
 */
export function isDriveEscape(event: MessageEvent, frame: HTMLIFrameElement | null): boolean {
  const own = frame?.contentWindow
  if (!own || event.source !== own) return false
  if (event.origin !== driveOrigin()) return false
  const data = event.data as { type?: unknown } | null
  return typeof data === 'object' && data !== null && data.type === DRIVE_ESCAPE
}

export function postDriveActive(frame: HTMLIFrameElement | null, active: boolean): void {
  const target = frame?.contentWindow
  if (!target) return
  const message: DriveActiveMessage = { type: DRIVE_ACTIVE, active }
  target.postMessage(message, driveOrigin())
}

/**
 * The operator's session ended: signed out, or the site refused the token.
 * The cockpit keeps the bridge key in its own tab storage, so it is told to
 * relinquish, forget the key and close, rather than leave the key to the
 * next operator or log an armed sign-out as link loss. Sent after
 * active=false, while the frame is still mounted.
 */
export const DRIVE_SIGNOUT = 'argus.drive.signout'

export interface DriveSignoutMessage {
  type: typeof DRIVE_SIGNOUT
}

export function postDriveSignout(frame: HTMLIFrameElement | null): void {
  const target = frame?.contentWindow
  if (!target) return
  const message: DriveSignoutMessage = { type: DRIVE_SIGNOUT }
  target.postMessage(message, driveOrigin())
}
