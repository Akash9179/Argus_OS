/**
 * Drive-access password, held in sessionStorage (cleared when the tab closes).
 *
 * This is a SHARED secret, and the static UI itself is public — so this gate is
 * only meaningful because the RELAY validates the same password server-side and
 * drops anyone who fails. The UI prompt is just how the operator supplies it.
 */
const KEY = 'argus.driveKey'

export function isDriveMode(): boolean {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).has('drive')
}

export function getDriveKey(): string | null {
  if (typeof window === 'undefined') return null
  return window.sessionStorage.getItem(KEY)
}

export function setDriveKey(pw: string): void {
  window.sessionStorage.setItem(KEY, pw)
}

export function clearDriveKey(): void {
  window.sessionStorage.removeItem(KEY)
}
