/** The vehicle camera's stream address, from the cockpit address
 *  (?video=<http url>). Only http and https are accepted: the value ends
 *  up in an <img src>, and nothing else belongs there. Null means no
 *  camera is named, and the cockpit says so rather than inventing one. */
export function videoUrlFromSearch(search: string, name = 'video'): string | null {
  const raw = new URLSearchParams(search).get(name)
  if (!raw) return null
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return null
  }
  return u.protocol === 'http:' || u.protocol === 'https:' ? raw : null
}

export type VideoFeeds =
  | { kind: 'pair'; left: string; right: string }
  | { kind: 'single'; url: string }

/** The vehicle's cameras named in the cockpit address. Two forward cameras
 *  side by side (?videoL= and ?videoR=, 5 Nov 2026) make one wide strip, with
 *  no stitching: their extrinsics are not known. One side alone, or ?video=,
 *  is a single feed. Null: no camera named. */
export function videoFeedsFromSearch(search: string): VideoFeeds | null {
  const left = videoUrlFromSearch(search, 'videoL')
  const right = videoUrlFromSearch(search, 'videoR')
  if (left && right) return { kind: 'pair', left, right }
  const one = left ?? right ?? videoUrlFromSearch(search, 'video')
  return one ? { kind: 'single', url: one } : null
}
