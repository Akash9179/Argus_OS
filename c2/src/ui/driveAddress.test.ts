/**
 * The key-stripping rule, shared by the build (vite.config.ts) and the
 * running page (driveUrl.ts). The build use is what keeps a key out of the
 * bundle: Vite writes VITE_ values into the JavaScript as literals.
 */
import { describe, expect, it } from 'vitest'
import { withoutKey } from './driveAddress'

describe('withoutKey', () => {
  it('removes a key and keeps every other part of the address', () => {
    expect(withoutKey('http://localhost:5174/?bridge=localhost:8090&key=s3cret#top')).toEqual({
      url: 'http://localhost:5174/?bridge=localhost%3A8090#top',
      hadKey: true,
    })
  })

  it('drops the question mark when the key was the only parameter', () => {
    expect(withoutKey('http://localhost:5174/?key=s3cret')).toEqual({ url: 'http://localhost:5174/', hadKey: true })
  })

  it('keeps a relative address relative', () => {
    expect(withoutKey('/drive/?key=s3cret&bridge=b:1').url).toBe('/drive/?bridge=b%3A1')
  })

  it('returns an address without a key exactly as given', () => {
    const raw = 'http://localhost:5174/?bridge=localhost:8090'
    expect(withoutKey(raw)).toEqual({ url: raw, hadKey: false })
  })

  it('does not mistake a key in the fragment for a query parameter', () => {
    const raw = 'http://localhost:5174/#key=not-a-param'
    expect(withoutKey(raw)).toEqual({ url: raw, hadKey: false })
  })
})
