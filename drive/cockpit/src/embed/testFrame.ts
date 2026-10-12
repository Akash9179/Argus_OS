/**
 * Test support only: place this window inside a parent frame, as C2 does,
 * and speak for that parent. Nothing in the app imports this file.
 */
import { DRIVE_ACTIVE, DRIVE_SIGNOUT, forgetDriveActive } from './driveActive'

export const FRAMER_ORIGIN = 'http://c2.test:5173'

let parentFrame: HTMLIFrameElement | null = null

/** Frame this window. The cockpit is then inactive until the parent speaks. */
export function enterFrame(): Window {
  parentFrame = document.createElement('iframe')
  document.body.appendChild(parentFrame)
  const parent = parentFrame.contentWindow!
  Object.defineProperty(window, 'parent', { value: parent, configurable: true })
  Object.defineProperty(document, 'referrer', { value: `${FRAMER_ORIGIN}/drive`, configurable: true })
  forgetDriveActive()
  return parent
}

/** Undo enterFrame. */
export function leaveFrame(): void {
  Object.defineProperty(window, 'parent', { value: window, configurable: true })
  Object.defineProperty(document, 'referrer', { value: '', configurable: true })
  parentFrame?.remove()
  parentFrame = null
  forgetDriveActive()
}

/** The parent says whether Drive is the active screen. Synchronous, no React flush. */
export function parentSays(active: boolean, source: Window = window.parent, origin = FRAMER_ORIGIN): void {
  window.dispatchEvent(new MessageEvent('message', { data: { type: DRIVE_ACTIVE, active }, source, origin }))
}

/** The parent signs the operator out, right before it unmounts the frame. */
export function parentSignsOut(source: Window = window.parent, origin = FRAMER_ORIGIN): void {
  window.dispatchEvent(new MessageEvent('message', { data: { type: DRIVE_SIGNOUT }, source, origin }))
}
