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

/** The right camera's offset in left-camera pixels (?merge=dx,dy). With a
 *  pair of feeds this overlaps them into one wide view. It is a fixed 2D
 *  offset measured once, not a calibration: things nearer or farther than
 *  where it was measured show a kink at the seam (5 Nov 2026). */
export function mergeFromSearch(search: string): { dx: number; dy: number } | null {
  const raw = new URLSearchParams(search).get('merge')
  if (!raw) return null
  const parts = raw.split(',')
  if (parts.length !== 2) return null
  const [dx, dy] = parts.map((p) => Number(p.trim()))
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return null
  if (Math.abs(dx) > 2000 || Math.abs(dy) > 2000) return null
  return { dx, dy }
}

export interface MergeLayout {
  width: number
  height: number
  left: { x: number; y: number }
  right: { x: number; y: number }
  /** the seam's feather on the right image, as fractions of its width */
  seamFrom: number
  seamTo: number
  /** the rows both frames cover: shown, the rest cropped, so no corner is black */
  crop: { y: number; height: number }
}

/** Both frames on one canvas, the right one at its offset, the seam in the
 *  middle of the overlap with a feather `feather` pixels wide. */
export function mergeLayout(o: { dx: number; dy: number }, w: number, h: number, feather: number): MergeLayout {
  const minX = Math.min(0, o.dx), minY = Math.min(0, o.dy)
  const maxX = Math.max(w, o.dx + w), maxY = Math.max(h, o.dy + h)
  const overlapFrom = Math.max(0, o.dx), overlapTo = Math.min(w, o.dx + w)
  const seamLeftPx = (overlapFrom + overlapTo) / 2
  const seamRightPx = seamLeftPx - o.dx
  return {
    width: maxX - minX,
    height: maxY - minY,
    left: { x: 0 - minX, y: 0 - minY },
    right: { x: o.dx - minX, y: o.dy - minY },
    seamFrom: Math.max(0, seamRightPx - feather / 2) / w,
    seamTo: Math.min(w, seamRightPx + feather / 2) / w,
    crop: {
      y: Math.max(0 - minY, o.dy - minY),
      height: Math.min(0 - minY + h, o.dy - minY + h) - Math.max(0 - minY, o.dy - minY),
    },
  }
}

/** The same ZED camera's colour-coded depth stream, by the wrapper's topic
 *  naming (…/rgb/color/rect/image → …/depth/depth_color), or null. */
export function depthUrlFor(url: string): string | null {
  const rgb = '/rgb/color/rect/image'
  return url.includes(rgb) ? url.replace(rgb, '/depth/depth_color') : null
}

export type CameraView = 'merged' | 'pair' | 'grid'

/** The views the operator can switch between, the default first. */
export function viewsFor(feeds: VideoFeeds | null, merge: { dx: number; dy: number } | null): CameraView[] {
  if (feeds?.kind !== 'pair') return []
  return merge ? ['merged', 'pair', 'grid'] : ['pair', 'grid']
}
