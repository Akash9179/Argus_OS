import { describe, expect, it } from 'vitest'
import { videoUrlFromSearch } from './videoSource'

// The vehicle's camera, 5 Nov 2026: an MJPEG stream from the Jetson's
// web_video_server, named in the cockpit address as ?video=<url>.
describe('videoUrlFromSearch', () => {
  it('returns nothing when no camera is named', () => {
    expect(videoUrlFromSearch('')).toBeNull()
    expect(videoUrlFromSearch('?bridge=localhost:8090')).toBeNull()
  })

  it('accepts an http or https stream address', () => {
    const url = 'http://100.116.120.118:8080/stream?topic=/zed_front/zed_node/rgb/color/rect/image'
    expect(videoUrlFromSearch('?video=' + encodeURIComponent(url))).toBe(url)
    expect(videoUrlFromSearch('?video=https://cam.example/s')).toBe('https://cam.example/s')
  })

  it('refuses anything that is not an http address', () => {
    expect(videoUrlFromSearch('?video=javascript:alert(1)')).toBeNull()
    expect(videoUrlFromSearch('?video=file:///etc/passwd')).toBeNull()
    expect(videoUrlFromSearch('?video=not a url')).toBeNull()
  })
})

// 5 Nov 2026: two forward ZED X cameras side by side for a wide view.
import { videoFeedsFromSearch } from './videoSource'

describe('videoFeedsFromSearch', () => {
  const L = 'http://100.116.120.118:8080/stream?topic=/zed_front/zed_node/rgb/color/rect/image'
  const R = 'http://100.116.120.118:8080/stream?topic=/zed_rear/zed_node/rgb/color/rect/image'
  const q = (o: Record<string, string>) => '?' + new URLSearchParams(o).toString()

  it('gives a left and right pair when both are named', () => {
    expect(videoFeedsFromSearch(q({ videoL: L, videoR: R }))).toEqual({ kind: 'pair', left: L, right: R })
  })

  it('falls back to the single feed, and to one side alone', () => {
    expect(videoFeedsFromSearch(q({ video: L }))).toEqual({ kind: 'single', url: L })
    expect(videoFeedsFromSearch(q({ videoL: L }))).toEqual({ kind: 'single', url: L })
    expect(videoFeedsFromSearch(q({ videoR: R }))).toEqual({ kind: 'single', url: R })
  })

  it('names no camera when none is given or none is an http address', () => {
    expect(videoFeedsFromSearch('')).toBeNull()
    expect(videoFeedsFromSearch(q({ videoL: 'javascript:alert(1)', videoR: 'file:///x' }))).toBeNull()
  })

  it('a pair wins over the single feed', () => {
    expect(videoFeedsFromSearch(q({ video: 'http://a/s', videoL: L, videoR: R }))).toEqual({ kind: 'pair', left: L, right: R })
  })
})

// 5 Nov 2026: the merged view, two forward cameras overlapped at a fixed
// offset (from the "x" mark seen by both) with a feathered seam.
import { mergeFromSearch, mergeLayout } from './videoSource'

describe('mergeFromSearch', () => {
  it('reads the right image offset in left-image pixels', () => {
    expect(mergeFromSearch('?merge=524,62')).toEqual({ dx: 524, dy: 62 })
    expect(mergeFromSearch('?merge=-10.5,0')).toEqual({ dx: -10.5, dy: 0 })
  })
  it('refuses anything that is not two finite numbers in range', () => {
    expect(mergeFromSearch('')).toBeNull()
    expect(mergeFromSearch('?merge=524')).toBeNull()
    expect(mergeFromSearch('?merge=a,b')).toBeNull()
    expect(mergeFromSearch('?merge=5000,0')).toBeNull()
  })
})

describe('mergeLayout', () => {
  it('places both 960x600 frames on one canvas and puts the seam mid-overlap', () => {
    const m = mergeLayout({ dx: 524, dy: 62 }, 960, 600, 60)
    expect(m.width).toBe(1484)
    expect(m.height).toBe(662)
    expect(m.left).toEqual({ x: 0, y: 0 })
    expect(m.right).toEqual({ x: 524, y: 62 })
    // overlap in left pixels 524..960, seam at 742; in right-image pixels 218 +- 30
    expect(m.seamFrom).toBeCloseTo(188 / 960, 5)
    expect(m.seamTo).toBeCloseTo(248 / 960, 5)
  })
  it('handles a right image above the left one', () => {
    const m = mergeLayout({ dx: 500, dy: -40 }, 960, 600, 60)
    expect(m.height).toBe(640)
    expect(m.left).toEqual({ x: 0, y: 40 })
    expect(m.right).toEqual({ x: 500, y: 0 })
  })
})

describe('mergeLayout crop', () => {
  it('keeps only the rows both cameras cover, so no black corners show', () => {
    const m = mergeLayout({ dx: 247, dy: 34 }, 960, 600, 60)
    expect(m.crop).toEqual({ y: 34, height: 566 })
    const up = mergeLayout({ dx: 500, dy: -40 }, 960, 600, 60)
    expect(up.crop).toEqual({ y: 40, height: 560 })
  })
})

// 5 Nov 2026: a view switcher (merged, side by side, grid) and the grid's depth tiles.
import { depthUrlFor, viewsFor } from './videoSource'

describe('depthUrlFor', () => {
  it("gives the same camera's colour-coded depth stream", () => {
    expect(depthUrlFor('http://h:8080/stream?topic=/zed_rear/zed_node/rgb/color/rect/image'))
      .toBe('http://h:8080/stream?topic=/zed_rear/zed_node/depth/depth_color')
  })
  it('gives nothing for a stream it does not recognise', () => {
    expect(depthUrlFor('http://h:8080/stream?topic=/other/image')).toBeNull()
  })
})

describe('viewsFor', () => {
  const pair = { kind: 'pair' as const, left: 'http://a', right: 'http://b' }
  it('offers merged first when a merge offset is set', () => {
    expect(viewsFor(pair, { dx: 1, dy: 2 })).toEqual(['merged', 'pair', 'grid'])
  })
  it('offers side by side and grid for a pair without an offset', () => {
    expect(viewsFor(pair, null)).toEqual(['pair', 'grid'])
  })
  it('offers no switcher for one feed or none', () => {
    expect(viewsFor({ kind: 'single', url: 'http://a' }, null)).toEqual([])
    expect(viewsFor(null, null)).toEqual([])
  })
})
