/**
 * What the map frames when it first opens.
 *
 * The bug this pins: the first fit framed every machine the server had ever
 * known, so one stale machine 500 km away left the site a speck in the
 * middle of an empty map. The site is its zones; failing that, the machines
 * that are answering; failing that, the machines heard from lately. A
 * machine silent for more than a day never pulls the frame.
 */
import { describe, expect, it } from 'vitest'
import type { Asset, Zone } from '../sdk/types'
import type { World } from '../state/world'
import { initialFrame, FRAME_SILENCE_SECONDS } from './frame'

const NOW = 1_800_000_000

function machine(id: string, lat: number, lon: number, heardAgo: number | undefined): Asset {
  return {
    asset_id: id,
    display_name: id,
    position: { latitude_deg: lat, longitude_deg: lon },
    last_heartbeat: heardAgo === undefined ? undefined : new Date((NOW - heardAgo) * 1000).toISOString(),
  }
}

function zone(id: string, ring: [number, number][]): Zone {
  return {
    zone_id: id,
    name: id,
    geometry: { exterior: ring.map(([lat, lon]) => ({ latitude_deg: lat, longitude_deg: lon })) },
  }
}

function world(assets: Asset[], zones: Zone[] = []): World {
  return {
    assets: new Map(assets.map((a) => [a.asset_id, a])),
    telemetry: new Map(),
    tracks: new Map(),
    zones: new Map(zones.map((z) => [z.zone_id, z])),
    tasks: new Map(),
    progress: new Map(),
    events: [],
  }
}

const answeringOnly =
  (...ids: string[]) =>
  (id: string) =>
    ids.includes(id)

describe('the first frame', () => {
  it('frames the site zones when there are any, whatever the machines are doing', () => {
    const fence = zone('Fence', [
      [23.19, 79.98],
      [23.2, 79.99],
      [23.18, 80.0],
    ])
    const w = world([machine('Near', 23.19, 79.99, 5), machine('Far', 51.5, -0.12, 5)], [fence])
    const frame = initialFrame(w, answeringOnly('Near', 'Far'), NOW)
    expect(frame?.points).toEqual([
      [23.19, 79.98],
      [23.2, 79.99],
      [23.18, 80.0],
    ])
  })

  it('frames the answering machines when the site has no zones', () => {
    const w = world([machine('Live', 23.19, 79.99, 5), machine('Quiet', 51.5, -0.12, 300)])
    expect(initialFrame(w, answeringOnly('Live'), NOW)?.points).toEqual([[23.19, 79.99]])
  })

  it('falls back to every machine heard lately when none is answering', () => {
    const w = world([machine('A', 23.19, 79.99, 300), machine('B', 23.2, 80.0, 3600)])
    expect(initialFrame(w, answeringOnly(), NOW)?.points).toEqual([
      [23.19, 79.99],
      [23.2, 80.0],
    ])
  })

  it('never lets a machine silent for more than a day pull the frame', () => {
    const w = world([
      machine('Recent', 23.19, 79.99, 3600),
      machine('Old', 51.5, -0.12, FRAME_SILENCE_SECONDS + 60),
    ])
    expect(initialFrame(w, answeringOnly(), NOW)?.points).toEqual([[23.19, 79.99]])
    // Not even when it is counted as answering, which every machine is
    // while our own link is down.
    expect(initialFrame(w, answeringOnly('Recent', 'Old'), NOW)?.points).toEqual([[23.19, 79.99]])
  })

  it('does not count a machine with no time heard as recent', () => {
    const w = world([machine('Unknown', 51.5, -0.12, undefined)])
    expect(initialFrame(w, answeringOnly(), NOW)).toBeNull()
  })

  it('frames nothing when nothing qualifies, so the map waits for something real', () => {
    const w = world([machine('Old', 51.5, -0.12, 3 * 86400)])
    expect(initialFrame(w, answeringOnly(), NOW)).toBeNull()
  })

  it('skips a zone with too few points to be an area', () => {
    const w = world(
      [machine('Live', 23.19, 79.99, 5)],
      [
        zone('Line', [
          [1, 1],
          [2, 2],
        ]),
      ],
    )
    expect(initialFrame(w, answeringOnly('Live'), NOW)?.points).toEqual([[23.19, 79.99]])
  })
})
