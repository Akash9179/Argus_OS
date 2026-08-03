/**
 * What C2 believes, tested where believing wrongly misleads an operator.
 */
import { describe, expect, it } from 'vitest'
import type { Asset, Telemetry } from '../sdk/types'
import { isAnswering, lastHeardAt, type World } from './world'

function aWorld(assets: Asset[] = [], telemetry: Telemetry[] = []): World {
  return {
    assets: new Map(assets.map((a) => [a.asset_id, a])),
    telemetry: new Map(telemetry.map((t) => [t.asset_id, t])),
    tracks: new Map(),
    zones: new Map(),
    tasks: new Map(),
    progress: new Map(),
    events: [],
  }
}

const NOW = 1_754_000_000

describe('lastHeardAt', () => {
  it('counts heartbeats as being heard, not just motion samples', () => {
    // Reading telemetry alone once claimed a machine had gone unheard
    // while the server had heard from it moments before.
    const asset: Asset = {
      asset_id: 'A1',
      display_name: 'One',
      last_heartbeat: new Date((NOW - 5) * 1000).toISOString(),
    }
    expect(lastHeardAt(aWorld([asset]), asset)).toBeCloseTo(NOW - 5, 0)
  })

  it('takes the later of heartbeat and telemetry', () => {
    const asset: Asset = {
      asset_id: 'A1',
      display_name: 'One',
      last_heartbeat: new Date((NOW - 60) * 1000).toISOString(),
    }
    const world = aWorld([asset], [{ asset_id: 'A1', timestamp: NOW - 3 }])
    expect(lastHeardAt(world, asset)).toBe(NOW - 3)
  })

  it('is undefined for a machine never heard from, never zero', () => {
    const asset: Asset = { asset_id: 'A1', display_name: 'One' }
    expect(lastHeardAt(aWorld([asset]), asset)).toBeUndefined()
  })
})

describe('isAnswering', () => {
  const fresh: Asset = {
    asset_id: 'A1',
    display_name: 'One',
    last_heartbeat: new Date((NOW - 5) * 1000).toISOString(),
  }
  const stale: Asset = {
    asset_id: 'A2',
    display_name: 'Two',
    last_heartbeat: new Date((NOW - 300) * 1000).toISOString(),
  }

  it('goes quiet after the silence threshold', () => {
    const world = aWorld([fresh, stale])
    expect(isAnswering(world, 'A1', NOW, false)).toBe(true)
    expect(isAnswering(world, 'A2', NOW, false)).toBe(false)
  })

  it('freezes while our own link is down', () => {
    // The disconnection law cuts both ways: our dropped stream must never
    // render as the vehicles dying.
    const world = aWorld([stale])
    expect(isAnswering(world, 'A2', NOW, true)).toBe(true)
  })

  it('never freezes a machine the server already called offline', () => {
    const offline: Asset = { ...fresh, status: 'ASSET_STATUS_OFFLINE' }
    const world = aWorld([offline])
    expect(isAnswering(world, 'A1', NOW, true)).toBe(false)
  })
})
