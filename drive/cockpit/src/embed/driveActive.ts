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
 *
 * This module is the single source of truth. Safety code reads
 * driveActiveNow() and subscribes with subscribeDriveActive(); both change
 * in the same turn as the message, with no React render in between. The
 * React hook is for display only.
 */
import { useSyncExternalStore } from 'react'

export const DRIVE_ACTIVE = 'argus.drive.active'

/** The cockpit asks C2 to return to the desktop: Esc inside the frame. */
export const DRIVE_ESCAPE = 'argus.drive.escape'

/**
 * C2 signs the operator out and is about to unmount this frame. The
 * cockpit disarms, forgets the stored key, and closes its socket cleanly,
 * all in the same turn. Same parent and origin checks as the active message.
 */
export const DRIVE_SIGNOUT = 'argus.drive.signout'

export interface DriveActiveMessage {
  type: typeof DRIVE_ACTIVE
  active: boolean
}

/** What the parent last said; null until it says anything. */
let heard: boolean | null = null
const listeners = new Set<() => void>()
const signOutListeners = new Set<() => void>()

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

/** True when this event came from the window that framed us, at its own origin. */
function fromFramer(e: MessageEvent): boolean {
  if (!isEmbedded() || e.source !== window.parent) return false
  const origin = framerOrigin()
  return origin !== null && e.origin === origin
}

/** The parent's verdict carried by this event, or null if the event is not one. */
export function readDriveActive(e: MessageEvent): boolean | null {
  if (!fromFramer(e)) return null
  const d = e.data as Partial<DriveActiveMessage> | null
  if (!d || typeof d !== 'object' || d.type !== DRIVE_ACTIVE || typeof d.active !== 'boolean') return null
  return d.active
}

/** True when this event is the framer's sign-out. */
export function readSignOut(e: MessageEvent): boolean {
  if (!fromFramer(e)) return false
  const d = e.data as { type?: unknown } | null
  return !!d && typeof d === 'object' && d.type === DRIVE_SIGNOUT
}

function onMessage(e: MessageEvent): void {
  if (readSignOut(e)) {
    notify(signOutListeners)
    return
  }
  const active = readDriveActive(e)
  if (active === null || active === heard) return
  heard = active
  notify(listeners)
}

/** Tell every subscriber. One that fails must not keep the others from hearing. */
function notify(set: Set<() => void>): void {
  for (const l of [...set]) {
    try {
      l()
    } catch (err) {
      console.error(err)
    }
  }
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

/** Called synchronously on every change of the active screen. Returns the unsubscribe. */
export function subscribeDriveActive(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Called synchronously when C2 signs the operator out. Returns the unsubscribe. */
export function subscribeSignOut(listener: () => void): () => void {
  signOutListeners.add(listener)
  return () => {
    signOutListeners.delete(listener)
  }
}

/** For display only. Safety code reads driveActiveNow() and subscribes directly. */
export function useDriveActive(): boolean {
  return useSyncExternalStore(subscribeDriveActive, driveActiveNow, () => true)
}

/** Forget what the parent said. Tests use it to start each case unheard. */
export function forgetDriveActive(): void {
  heard = null
  notify(listeners)
}
