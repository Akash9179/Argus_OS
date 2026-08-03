/**
 * The shapes the world model serves.
 *
 * These mirror the service interfaces, not the database and not the wire
 * protos. Field names keep their server spelling so a reader can hold one
 * vocabulary in their head.
 *
 * Every enum-shaped field is typed as `string`, never as a closed union.
 * The contract's enums are open: a newer machine may send a value this
 * build has never heard of, and the server passes it through rather than
 * dropping it. A closed union here would put the value back on the floor.
 */

export interface Position {
  latitude_deg?: number
  longitude_deg?: number
  altitude_m?: number
}

export interface Velocity {
  north_mps?: number
  east_mps?: number
  down_mps?: number
}

/** Who is signed in. Never carries the identifier the server knows them by. */
export interface Principal {
  display_name: string
  role: string
}

export interface Asset {
  asset_id: string
  /** Resolved by the server. C2 never composes a name. */
  display_name: string
  asset_class?: string
  capabilities?: Record<string, unknown>
  status?: string
  position?: Position
  battery_fraction?: number
  last_heartbeat?: string
}

export interface Telemetry {
  asset_id: string
  position?: Position
  heading_deg?: number
  speed_mps?: number
  /** Seconds since the epoch. */
  timestamp: number
}

export interface TrackHistoryPoint {
  timestamp?: string
  position?: Position
  velocity?: Velocity
}

export interface Track {
  track_id: string
  /** Resolved by the server, hedge included. C2 never composes a name. */
  display_name?: string
  /** Where it is, in words. Empty when it is in no zone we know. */
  place?: string
  entity_id?: string
  state?: string
  position?: Position
  velocity?: Velocity
  confidence?: number
  contributing_asset_ids?: string[]
  observation_ids?: string[]
  history?: TrackHistoryPoint[]
}

export interface Entity {
  entity_id: string
  entity_class?: string
  labels?: Record<string, string>
}

export interface TaskStatusPoint {
  state?: string
  timestamp?: string
  message?: string
}

export interface Task {
  task_id: string
  asset_id: string
  task_type: string
  parameters?: { waypoints?: Position[]; target_track_id?: string; speed_mps?: number }
  status?: string
  issued_by?: { principal_id?: string; channel?: string }
  /** Who gave the order, as a name. Resolved by the server. */
  ordered_by?: string
  /** Why the machine is doing this, already a phrase. Composed by the server. */
  reason?: string
  status_history?: TaskStatusPoint[]
}

export interface TaskProgress {
  task: Task
  progress?: number
  eta_sec?: number | null
  message?: string
}

export interface Zone {
  zone_id: string
  name?: string
  zone_type?: string
  geometry?: { exterior?: Position[] }
}

/** Already a plain sentence when it arrives. C2 never rewrites it. */
export interface WorldEvent {
  event_id: string
  ts: number
  text: string
  severity: string
  source: string
  subject_kind?: string
  subject_id?: string
}

export interface Snapshot {
  assets: Asset[]
  telemetry: Telemetry[]
  tracks: Track[]
  zones: Zone[]
  tasks: Task[]
  events: WorldEvent[]
}

/** The live envelope kinds the server publishes. */
export type Envelope =
  | { kind: 'snapshot'; data: Snapshot }
  | { kind: 'asset.updated'; data: Asset }
  | { kind: 'asset.telemetry'; data: Telemetry }
  | { kind: 'track.updated'; data: Track }
  /**
   * A task never travels bare: the envelope carries how far along it is and
   * whatever the machine last said about it, which are transient facts that
   * do not belong in the durable task record.
   */
  | { kind: 'task.updated'; data: TaskProgress }
  | { kind: 'event.created'; data: WorldEvent }
  | { kind: 'zone.updated'; data: Zone }
  /** An envelope kind added after this build shipped. Kept, never dropped. */
  | { kind: string; data: unknown }

export interface TaskRequest {
  asset_id: string
  task_type: string
  waypoints?: Position[]
  target_track_id?: string
  speed_mps?: number
  priority?: number
  /** How the order reached the system, for the audit trail. */
  channel?: string
}
