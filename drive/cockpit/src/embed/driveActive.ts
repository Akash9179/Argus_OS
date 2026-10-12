/**
 * Is Drive the operator's active screen?
 *
 * C2 hosts this cockpit in an iframe and keeps the frame mounted while the
 * operator works in another application. Founder decision, 12 Oct 2026:
 * leaving Drive relinquishes control. C2 posts
 * { type: 'argus.drive.active', active } to this frame on every change of
 * the active screen, and once when the frame loads.
 *
 * Only the parent window may say this, and only from the origin of the page
 * that framed us (document.referrer). An embedded cockpit that has heard
 * nothing yet is inactive. A standalone cockpit is always active.
 *
 * The listener is attached when this module loads, before React renders,
 * so the message C2 sends on frame load is never missed.
 */
import { useSyncExternalStore } from 'react'

export const DRIVE_ACTIVE = 'argus.drive.active'

/** The cockpit asks C2 to return to the desktop: Esc inside the frame. */
export const DRIVE_ESCAPE = 'argus.drive.escape'

export interface DriveActiveMessage {
  type: typeof DRIVE_ACTIVE
  active: boolean
}

/** What the parent last said; null until it says anything. */
let heard: boolean | null = null
const listeners = new Set<() => void>()

export function isEmbedded(): boolean {
  return typeof window !== 'undefined' && window.parent !== window
}

/** The origin of the page that framed us, or null when it cannot be told. */
export function framerOrigin(): string | null {
  if (typeof document === 'undefined' || !document.referrer) return null
  try {
    const origin = new URL(document.referrer).origin
    return origin === 'null' ? null : origin
  } catch {
    return null
  }
}

/** The parent's verdict carried by this event, or null if the event is not one. */
export function readDriveActive(e: MessageEvent): boolean | null {
  if (!isEmbedded() || e.source !== window.parent) return null
  const origin = framerOrigin()
  if (origin === null || e.origin !== origin) return null
  const d = e.data as Partial<DriveActiveMessage> | null
  if (!d || typeof d !== 'object' || d.type !== DRIVE_ACTIVE || typeof d.active !== 'boolean') return null
  return d.active
}

function onMessage(e: MessageEvent): void {
  const active = readDriveActive(e)
  if (active === null || active === heard) return
  heard = active
  for (const l of listeners) l()
}

if (typeof window !== 'undefined') window.addEventListener('message', onMessage)

/**
 * Ask the framing page to return to the desktop. Sent only to the framer's
 * own origin; when that origin is unknown, nothing is sent.
 */
export function postEscape(): void {
  if (!isEmbedded()) return
  const origin = framerOrigin()
  if (origin === null) return
  window.parent.postMessage({ type: DRIVE_ESCAPE }, origin)
}

/** True when this cockpit may command the vehicle as the active screen. */
export function driveActiveNow(): boolean {
  return isEmbedded() ? heard === true : true
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useDriveActive(): boolean {
  return useSyncExternalStore(subscribe, driveActiveNow, () => true)
}

/** Forget what the parent said. Tests use it to start each case unheard. */
export function forgetDriveActive(): void {
  heard = null
  for (const l of listeners) l()
}
