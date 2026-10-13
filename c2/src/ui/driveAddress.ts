/**
 * The Drive address with any bridge key taken out.
 *
 * Pure, so the build and the page share one rule. vite.config.ts applies it
 * to VITE_DRIVE_URL before Vite writes that value into the bundle, and
 * driveUrl.ts applies it again to whatever the page reads at run time
 * (localStorage included). Configuration holds the address only; the
 * cockpit asks the operator for the key.
 */
export function withoutKey(raw: string): { url: string; hadKey: boolean } {
  const hashAt = raw.indexOf('#')
  const beforeHash = hashAt < 0 ? raw : raw.slice(0, hashAt)
  const hash = hashAt < 0 ? '' : raw.slice(hashAt)
  const queryAt = beforeHash.indexOf('?')
  if (queryAt < 0) return { url: raw, hadKey: false }
  const params = new URLSearchParams(beforeHash.slice(queryAt + 1))
  if (!params.has('key')) return { url: raw, hadKey: false }
  params.delete('key')
  const rest = params.toString()
  return { url: beforeHash.slice(0, queryAt) + (rest ? `?${rest}` : '') + hash, hadKey: true }
}
