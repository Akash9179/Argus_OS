/**
 * The Drive address, tested where a mistake would ship a credential.
 *
 * Vite inlines every VITE_ variable into the client bundle, so a bridge key
 * written into VITE_DRIVE_URL would be readable by anyone holding the
 * build. C2 accepts only the address and leaves the key to the cockpit.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

function memoryStorage(): Storage {
  const m = new Map<string, string>()
  return {
    get length() { return m.size },
    clear: () => m.clear(),
    getItem: (k: string) => m.get(k) ?? null,
    key: (i: number) => [...m.keys()][i] ?? null,
    removeItem: (k: string) => { m.delete(k) },
    setItem: (k: string, v: string) => { m.set(k, String(v)) },
  }
}

async function freshModule() {
  vi.resetModules()
  return import('./driveUrl')
}

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage())
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('driveUrl', () => {
  it('drops a key written into VITE_DRIVE_URL, and says so once', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubEnv('VITE_DRIVE_URL', 'http://localhost:5174/?bridge=localhost:8090&key=s3cret')
    const { driveUrl } = await freshModule()
    const url = new URL(driveUrl())
    expect(url.searchParams.get('key')).toBeNull()
    expect(url.searchParams.get('bridge')).toBe('localhost:8090')
    expect(driveUrl()).not.toContain('s3cret')
    expect(warn).toHaveBeenCalledTimes(1)
  })

  it('drops a key stored in localStorage', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.localStorage.setItem('argus.driveUrl', 'http://10.0.0.5:5174/?key=s3cret&bridge=10.0.0.9:8090')
    const { driveUrl } = await freshModule()
    expect(driveUrl()).toBe('http://10.0.0.5:5174/?bridge=10.0.0.9%3A8090')
  })

  it('leaves an address without a key exactly as configured', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.stubEnv('VITE_DRIVE_URL', 'http://localhost:5174/?bridge=localhost:8090')
    const { driveUrl } = await freshModule()
    expect(driveUrl()).toBe('http://localhost:5174/?bridge=localhost:8090')
    expect(warn).not.toHaveBeenCalled()
  })
})
