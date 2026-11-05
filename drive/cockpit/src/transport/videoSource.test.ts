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
