/**
 * Drive-access password, held in sessionStorage (cleared when the tab closes).
 *
 * This is a SHARED secret, and the static UI itself is public — so this gate is
 * only meaningful because the RELAY validates the same password server-side and
 * drops anyone who fails. The UI prompt is just how the operator supplies it.
 */
const KEY = 'argus.driveKey'

// Testing convenience: ?key=<password> in the URL pre-fills the drive key so
// the OS shell can open the cockpit without a prompt. TESTING PERIOD ONLY —
// a key in a URL is not an acceptable pattern past the bench, remove this
// before anything reachable from outside the bench exists.
if (typeof window !== 'undefined') {
  const urlKey = new URLSearchParams(window.location.search).get('key')
  if (urlKey) window.sessionStorage.setItem(KEY, urlKey)
}

export function isDriveMode(): boolean {
  if (typeof window === 'undefined') return false
  const q = new URLSearchParams(window.location.search)
  return q.has('drive') || q.has('bridge')
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
