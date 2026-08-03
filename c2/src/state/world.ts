/**
 * What C2 believes about the world.
 *
 * A snapshot arrives first, then envelopes amend it. This module holds no
 * opinions: it stores what the server said. Judgements about what is worth
 * showing belong in the interface, and judgements about what is true belong
 * in the world model.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { openStream, type Link } from '../sdk/stream'
import type {
  Asset,
  Envelope,
  Snapshot,
  Task,
  TaskProgress,
  Telemetry,
  Track,
  WorldEvent,
  Zone,
} from '../sdk/types'

export interface World {
  assets: Map<string, Asset>
  telemetry: Map<string, Telemetry>
  tracks: Map<string, Track>
  zones: Map<string, Zone>
  tasks: Map<string, Task>
  /** How far along each open order is, and the machine's own last word on it. */
  progress: Map<string, TaskProgress>
  events: WorldEvent[]
}

const empty = (): World => ({
  assets: new Map(),
  telemetry: new Map(),
  tracks: new Map(),
  zones: new Map(),
  tasks: new Map(),
  progress: new Map(),
  events: [],
})

const MAX_EVENTS = 200

function apply(world: World, envelope: Envelope): World {
  const next: World = { ...world }

  switch (envelope.kind) {
    case 'snapshot': {
      const data = envelope.data as Snapshot
      next.assets = new Map(data.assets.map((a) => [a.asset_id, a]))
      next.telemetry = new Map(data.telemetry.map((t) => [t.asset_id, t]))
      next.tracks = new Map(data.tracks.map((t) => [t.track_id, t]))
      next.zones = new Map(data.zones.map((z) => [z.zone_id, z]))
      next.tasks = new Map(data.tasks.map((t) => [t.task_id, t]))
      next.events = [...data.events].sort((a, b) => b.ts - a.ts).slice(0, MAX_EVENTS)
      return next
    }
    case 'asset.updated': {
      const asset = envelope.data as Asset
      next.assets = new Map(world.assets).set(asset.asset_id, asset)
      return next
    }
    case 'asset.telemetry': {
      const sample = envelope.data as Telemetry
      next.telemetry = new Map(world.telemetry).set(sample.asset_id, sample)
      return next
    }
    case 'track.updated': {
      const track = envelope.data as Track
      next.tracks = new Map(world.tracks).set(track.track_id, track)
      return next
    }
    case 'task.updated': {
      // The envelope wraps the task with its progress. Unwrap it here so the
      // rest of the application only ever handles one shape.
      const update = envelope.data as TaskProgress
      if (!update?.task?.task_id) return world
      next.tasks = new Map(world.tasks).set(update.task.task_id, update.task)
      next.progress = new Map(world.progress).set(update.task.task_id, update)
      return next
    }
    case 'zone.updated': {
      const zone = envelope.data as Zone
      next.zones = new Map(world.zones).set(zone.zone_id, zone)
      return next
    }
    case 'event.created': {
      const event = envelope.data as WorldEvent
      next.events = [event, ...world.events].slice(0, MAX_EVENTS)
      return next
    }
    default:
      // An envelope kind added after this build shipped. Ignoring it is
      // correct; refusing the connection over it would not be.
      return world
  }
}

export function useWorld() {
  const [world, setWorld] = useState<World>(empty)
  const [link, setLink] = useState<Link>('connecting')
  /** Set once the first snapshot has landed, so we never draw an empty map. */
  const [ready, setReady] = useState(false)

  // Envelopes arrive faster than React should re-render, so they are
  // buffered and flushed on an animation frame. The map stays smooth and
  // no update is dropped.
  const pending = useRef<Envelope[]>([])
  const frame = useRef<number>()

  const flush = useCallback(() => {
    frame.current = undefined
    if (pending.current.length === 0) return
    const batch = pending.current
    pending.current = []
    setWorld((current) => batch.reduce(apply, current))
  }, [])

  useEffect(() => {
    const close = openStream({
      onEnvelope: (envelope) => {
        if (envelope.kind === 'snapshot') setReady(true)
        pending.current.push(envelope)
        if (frame.current === undefined) frame.current = requestAnimationFrame(flush)
      },
      onLink: setLink,
    })
    return () => {
      close()
      if (frame.current !== undefined) cancelAnimationFrame(frame.current)
    }
  }, [flush])

  return { world, link, ready }
}

/* ---------- reading the world ---------- */

/** Our machines, named, most recently heard from first. */
export function useMachines(world: World) {
  return useMemo(
    () =>
      [...world.assets.values()].sort((a, b) =>
        (b.last_heartbeat ?? '').localeCompare(a.last_heartbeat ?? ''),
      ),
    [world.assets],
  )
}

/** Things seen that are not ours, most confident first. */
export function useContacts(world: World) {
  return useMemo(
    () =>
      [...world.tracks.values()]
        .filter((t) => t.state !== 'TRACK_STATE_CLOSED')
        .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)),
    [world.tracks],
  )
}

const OPEN_TASK_STATES = new Set([
  'TASK_STATE_PENDING',
  'TASK_STATE_ACCEPTED',
  'TASK_STATE_RUNNING',
])

export function openTaskFor(world: World, assetId: string): Task | undefined {
  return [...world.tasks.values()].find(
    (t) => t.asset_id === assetId && OPEN_TASK_STATES.has(t.status ?? ''),
  )
}

/** A machine unheard from for this long has gone quiet. */
export const SILENCE_SECONDS = 30

/**
 * Is this machine still answering?
 *
 * `linkLost` freezes the judgement. When it is our own stream that has
 * dropped, every machine would otherwise fall silent at the same moment and
 * the interface would report our link failure as the vehicles dying. The
 * disconnection law cuts both ways: losing the link must never look like
 * losing the force.
 */
/**
 * When we last heard from a machine, by any means, or undefined if we never
 * have. Motion samples and heartbeats both count, and the later of the two
 * wins: a machine that is still beating has been heard from, whether or not
 * this application has seen it move.
 *
 * Everything that talks about silence reads from here, so the map and the
 * force rail can never disagree about when a machine was last heard.
 */
export function lastHeardAt(world: World, asset: Asset | undefined): number | undefined {
  if (!asset) return undefined
  const live = world.telemetry.get(asset.asset_id)?.timestamp
  const parsed = asset.last_heartbeat ? Date.parse(asset.last_heartbeat) / 1000 : NaN
  const beat = Number.isNaN(parsed) ? undefined : parsed
  const heard = Math.max(live ?? 0, beat ?? 0)
  return heard === 0 ? undefined : heard
}

export function isAnswering(world: World, assetId: string, now: number, linkLost: boolean): boolean {
  const asset = world.assets.get(assetId)
  if (asset?.status === 'ASSET_STATUS_OFFLINE') return false
  if (linkLost) return true
  const heard = lastHeardAt(world, asset)
  if (heard === undefined) return false
  return now - heard < SILENCE_SECONDS
}

export function positionOf(world: World, asset: Asset): { lat: number; lon: number } | null {
  const live = world.telemetry.get(asset.asset_id)?.position ?? asset.position
  if (live?.latitude_deg === undefined || live?.longitude_deg === undefined) return null
  return { lat: live.latitude_deg, lon: live.longitude_deg }
}
