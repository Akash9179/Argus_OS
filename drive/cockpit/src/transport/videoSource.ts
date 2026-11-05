/** The vehicle camera's stream address, from the cockpit address
 *  (?video=<http url>). Only http and https are accepted: the value ends
 *  up in an <img src>, and nothing else belongs there. Null means no
 *  camera is named, and the cockpit says so rather than inventing one. */
export function videoUrlFromSearch(search: string): string | null {
  const raw = new URLSearchParams(search).get('video')
  if (!raw) return null
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return null
  }
  return u.protocol === 'http:' || u.protocol === 'https:' ? raw : null
}
