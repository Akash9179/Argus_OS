/**
 * What the map frames when it first opens.
 *
 * The site is its zones. Without zones, it is where the answering machines
 * are; without those, where the machines heard from lately are. A machine
 * silent for more than a day never pulls the frame: one stale machine far
 * away used to leave the site a speck in an empty map.
 *
 * Contacts do not pull the frame either. They are drawn wherever they are,
 * and the operator finds them from the rail.
 */

import { lastHeardAt, positionOf, type World } from '../state/world'

/** A machine unheard for longer than this is history, not the site. */
export const FRAME_SILENCE_SECONDS = 24 * 60 * 60

export interface Frame {
  points: [number, number][]
  /** How much room to leave around the points, as a fraction of their span. */
  padding: number
}

export function initialFrame(world: World, answering: (assetId: string) => boolean, now: number): Frame | null {
  const zonePoints: [number, number][] = []
  for (const zone of world.zones.values()) {
    const ring = (zone.geometry?.exterior ?? [])
      .filter((p) => p.latitude_deg !== undefined && p.longitude_deg !== undefined)
      .map((p) => [p.latitude_deg!, p.longitude_deg!] as [number, number])
    if (ring.length >= 3) zonePoints.push(...ring)
  }
  if (zonePoints.length > 0) return { points: zonePoints, padding: 0.08 }

  // Heard within the day, by any means. A machine with no time heard is
  // not known to be recent, so it does not count as recent.
  const recent = [...world.assets.values()].filter((asset) => {
    const heard = lastHeardAt(world, asset)
    return heard !== undefined && now - heard <= FRAME_SILENCE_SECONDS
  })
  const placed = (assets: typeof recent) =>
    assets
      .map((asset) => positionOf(world, asset))
      .filter((at): at is { lat: number; lon: number } => at !== null)
      .map((at) => [at.lat, at.lon] as [number, number])
  const answeringPoints = placed(recent.filter((asset) => answering(asset.asset_id)))
  const points = answeringPoints.length > 0 ? answeringPoints : placed(recent)
  return points.length > 0 ? { points, padding: 1.2 } : null
}
