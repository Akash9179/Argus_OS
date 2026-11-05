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
