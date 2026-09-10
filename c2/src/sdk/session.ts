/**
 * The session: one token, and one place that knows when it stopped working.
 *
 * A stored token can be revoked while this tab is open, or between one day
 * and the next. Every interface reports that the same way (401 on REST,
 * close code 4401 on the stream), and every report ends here: the token is
 * forgotten and the application is told to show sign-in again.
 *
 * Without this the station used to sit at "site link down" for ever after a
 * refused token, which is a lie: the site was fine, we were not allowed in.
 */

const TOKEN_KEY = 'argus.token'

export function savedToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) ?? ''
}

export function saveToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function forgetToken(): void {
  window.localStorage.removeItem(TOKEN_KEY)
}

type Listener = () => void
const listeners = new Set<Listener>()

/** Be told when the token stops being accepted. Returns the unsubscribe. */
export function onSignedOut(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/**
 * The token was refused by the server (or the operator signed out). The
 * token is dropped first so that nothing racing this call can reuse it.
 */
export function signOut(): void {
  const had = savedToken() !== ''
  forgetToken()
  if (!had) return
  for (const listener of [...listeners]) listener()
}
