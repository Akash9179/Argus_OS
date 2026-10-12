/**
 * Operate: the one screen.
 *
 * Fleet on the left, the site in the middle (map, then the selected
 * machine's camera and readings, then what happened and what the machine
 * says about itself), and the assistant on the right. Nothing nests.
 * Anything that needs more room opens over the map and closes back.
 *
 * Everything on it is something a service said. Where a service has said
 * nothing, the screen says so in words rather than drawing a placeholder
 * that could be mistaken for a reading.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { track as api, Refused } from '../sdk/client'
import type { Link } from '../sdk/stream'
import type { Asset, Position, SystemsView, Task, TileLayerInfo, Track, WorldEvent } from '../sdk/types'
import {
  isAnswering,
  lastHeardAt,
  openTaskFor,
  positionOf,
  useContacts,
  useMachines,
  type World,
} from '../state/world'
import { Assistant } from './Assistant'
import { MapView } from './MapView'
import {
  agoInWords,
  assetStatus,
  clockAt,
  modeInWords,
  outOfTen,
  plain,
  say,
  severityStatus,
  statusInWords,
  type Status,
} from './wording'

/**
 * A mode is server vocabulary and open, like every other enum-shaped value
 * the contract carries. Typed as a string so a mode a newer server holds
 * reaches the operator as itself, rather than being forced into one of the
 * two this build happens to know.
 */
type Mode = string

interface Props {
  world: World
  link: Link
  theme: 'dark' | 'day'
}

export function Operate({ world, link, theme }: Props) {
  const [now, setNow] = useState(() => Date.now() / 1000)
  const machines = useMachines(world, now, link === 'lost')
  const contacts = useContacts(world)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string>('')
  const [classFilter, setClassFilter] = useState<string>('')
  const [showZones, setShowZones] = useState(true)
  const [showMachines, setShowMachines] = useState(true)
  const [tileLayers, setTileLayers] = useState<TileLayerInfo[]>([])
  const [imageryOn, setImageryOn] = useState(true)
  // Held with the machine it describes, so a newly selected machine never
  // shows the last machine's systems while its own answer is on the way.
  const [systemsOf, setSystemsOf] = useState<{ assetId: string; view: SystemsView | null } | null>(null)
  const [proposalPath, setProposalPath] = useState<Position[] | null>(null)
  const [focus, setFocus] = useState<{ lat: number; lon: number; key: number } | null>(null)
  const [assistantAway, setAssistantAway] = useState(false)

  // One clock for the whole screen, so every "how long ago" agrees.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => window.clearInterval(timer)
  }, [])

  // Select the first machine as soon as one appears, so the screen is never
  // waiting for a click to become useful. This adjusts state during render
  // rather than in an effect, so no frame is drawn with nothing selected.
  if (selectedAssetId === null && machines.length > 0) setSelectedAssetId(machines[0].asset_id)

  // Imagery is whatever this station has cached. Asked once; an empty
  // answer keeps the drawn terrain and says so on the map.
  useEffect(() => {
    let alive = true
    api
      .tiles()
      .then((found) => alive && setTileLayers(found.layers))
      .catch(() => alive && setTileLayers([]))
    return () => {
      alive = false
    }
  }, [])

  // What the selected machine has said about itself. Refreshed slowly:
  // registries change on boot, not every second.
  useEffect(() => {
    if (!selectedAssetId) return
    let alive = true
    const ask = () =>
      api
        .systems(selectedAssetId)
        .then((view) => alive && setSystemsOf({ assetId: selectedAssetId, view }))
        .catch(() => alive && setSystemsOf({ assetId: selectedAssetId, view: null }))
    void ask()
    const timer = window.setInterval(ask, 30_000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [selectedAssetId])

  const answering = useCallback(
    (assetId: string) => isAnswering(world, assetId, now, link === 'lost'),
    [world, now, link],
  )

  const selected = selectedAssetId ? world.assets.get(selectedAssetId) ?? null : null
  const systems = systemsOf && systemsOf.assetId === selectedAssetId ? systemsOf.view : null
  const selectedTrack = selectedTrackId ? world.tracks.get(selectedTrackId) ?? null : null
  const openTask = selected ? openTaskFor(world, selected.asset_id) : undefined
  /**
   * The selected machine's mode, as the server holds it. Never local
   * state: a toggle that moved before the server agreed would be showing
   * an operator a setting that is not in force anywhere.
   */
  const mode: Mode = selected?.autonomy ?? ''
  /**
   * Whether this machine can be sent somewhere from here, and if not, the
   * true reason. Computed once so every place that mentions it agrees.
   */
  const sending: { can: boolean; why: string } = !selected
    ? { can: false, why: say.map.noMachineSelected }
    : !answering(selected.asset_id)
      ? { can: false, why: say.map.cannotSend }
      : mode === 'automatic'
        ? { can: false, why: say.map.cannotSendAutomatic }
        : mode && mode !== 'manual'
          ? { can: false, why: say.map.cannotSendUnknownMode(modeInWords(mode)) }
          : // Manual, or a server too old to say. Tasking stays available in
            // both cases: refusing would strand an operator against a server
            // that works.
            { can: true, why: say.map.clickToSend }
  const canSend = sending.can

  const send = useCallback(
    async (lat: number, lon: number, channel: string, targetTrackId?: string) => {
      if (!selected) return
      try {
        await api.issueTask({
          asset_id: selected.asset_id,
          task_type: 'navigate',
          waypoints: [{ latitude_deg: lat, longitude_deg: lon }],
          target_track_id: targetTrackId ?? '',
          channel,
        })
        setNotice('')
      } catch (error) {
        // The server words its own refusals. We show what it said.
        setNotice(error instanceof Refused && error.message ? error.message : say.errors.orderFailed)
      }
    },
    [selected],
  )

  const stop = useCallback(async () => {
    if (!openTask) return
    try {
      await api.cancelTask(openTask.task_id)
    } catch (error) {
      setNotice(error instanceof Refused && error.message ? error.message : say.errors.orderFailed)
    }
  }, [openTask])

  /**
   * Ask the platform to change this machine's mode. Nothing is cancelled
   * here and nothing is issued here: switching the mode is itself the act,
   * and the platform withdraws what it started.
   */
  const switchMode = async (next: Mode) => {
    if (!selected || next === mode) return
    try {
      await api.setAutonomy(selected.asset_id, next)
      setNotice(next === 'automatic' ? say.mode.switchedToAutomatic : say.mode.switchedToManual)
    } catch (error) {
      setNotice(error instanceof Refused && error.message ? error.message : say.errors.modeFailed)
    }
  }

  /** Find a place or a machine by name and fly there. */
  const find = (text: string) => {
    const needle = text.trim().toLowerCase()
    if (!needle) return
    const machine = machines.find((m) => m.display_name.toLowerCase().includes(needle))
    const at = machine ? positionOf(world, machine) : null
    if (machine && at) {
      setSelectedAssetId(machine.asset_id)
      setFocus({ ...at, key: Date.now() })
      return
    }
    const zone = [...world.zones.values()].find((z) => (z.name ?? '').toLowerCase().includes(needle))
    const ring = zone?.geometry?.exterior?.filter((p) => p.latitude_deg !== undefined) ?? []
    if (ring.length > 0) {
      const lat = ring.reduce((s, p) => s + p.latitude_deg!, 0) / ring.length
      const lon = ring.reduce((s, p) => s + p.longitude_deg!, 0) / ring.length
      setFocus({ lat, lon, key: Date.now() })
    }
  }

  const imagery = imageryOn && tileLayers.length > 0 ? tileLayers[0] : null
  const zoneNames = useMemo(
    () => [...world.zones.values()].map((z) => z.name ?? '').filter(Boolean),
    [world.zones],
  )

  return (
    <div className={`operate${assistantAway ? ' is-assistant-away' : ''}`}>
      <FleetRail
        world={world}
        machines={machines}
        contacts={contacts}
        now={now}
        answering={answering}
        classFilter={classFilter}
        onClassFilter={setClassFilter}
        selectedAssetId={selectedAssetId}
        selectedTrackId={selectedTrackId}
        onSelectAsset={setSelectedAssetId}
        onSelectTrack={setSelectedTrackId}
      />

      <div className="col-centre">
        <div className="card map-card">
          <MapView
            world={world}
            theme={theme}
            selectedAssetId={selectedAssetId}
            selectedTrackId={selectedTrackId}
            answering={answering}
            canSend={canSend}
            onSelectAsset={setSelectedAssetId}
            onSelectTrack={setSelectedTrackId}
            onSendTo={(lat, lon) => void send(lat, lon, 'map')}
            proposalPath={proposalPath}
            imagery={imagery}
            showZones={showZones}
            showMachines={showMachines}
            focus={focus}
          />
          <form
            className="map-find"
            onSubmit={(event) => {
              event.preventDefault()
              find((new FormData(event.currentTarget).get('q') as string) ?? '')
            }}
          >
            <SearchGlyph />
            <input name="q" placeholder={say.find.placeholder} aria-label={say.find.placeholder} />
          </form>
          <div className="map-layers" role="group">
            {tileLayers.length > 0 && (
              <button className={`lbtn${imageryOn ? ' on' : ''}`} onClick={() => setImageryOn(!imageryOn)}>
                {say.operate.map.imagery}
              </button>
            )}
            <button className={`lbtn${showZones ? ' on' : ''}`} onClick={() => setShowZones(!showZones)}>
              <span className="dot is-act" />
              {say.operate.map.zones}
            </button>
            <button className={`lbtn${showMachines ? ' on' : ''}`} onClick={() => setShowMachines(!showMachines)}>
              <span className="dot is-ok" />
              {say.operate.map.machines}
            </button>
            <span className="lbtn is-inert" title={say.notBuiltYet}>
              <span className="dot is-sel" />
              {say.operate.map.marks}
            </span>
          </div>
          <div className="map-credit">
            {imagery ? [say.operate.map.credit, imagery.attribution].filter(Boolean).join(' · ') : say.operate.map.noImagery}
          </div>
          {/* A map that quietly ignores clicks teaches an operator that the
              system is unreliable, so it always states where it stands. */}
          {selected && <div className="map-hint">{sending.why}</div>}
          {link === 'lost' && <div className="map-warning">{say.link.lostDetail}</div>}
          {notice && <div className="map-notice">{notice}</div>}
          {selectedTrack && (
            <ContactDetail
              contact={selectedTrack}
              world={world}
              now={now}
              canSend={canSend}
              cannotSendWhy={sending.why}
              machineName={selected?.display_name ?? ''}
              onSend={() =>
                void send(
                  selectedTrack.position!.latitude_deg!,
                  selectedTrack.position!.longitude_deg!,
                  'map',
                  selectedTrack.track_id,
                )
              }
              onClose={() => setSelectedTrackId(null)}
            />
          )}
        </div>

        <div className="row-camera">
          <CameraCard machine={selected} systems={systems} />
          <ReadingsCard
            machine={selected}
            world={world}
            now={now}
            answering={selected ? answering(selected.asset_id) : false}
            systems={systems}
            mode={mode}
            task={openTask}
            onMode={switchMode}
            onStop={() => void stop()}
          />
        </div>

        <div className="row-activity">
          <ActivityCard events={world.events} />
          <CamerasCard machine={selected} systems={systems} />
          <SystemsCard machine={selected} systems={systems} />
        </div>
      </div>

      <Assistant
        machineName={selected?.display_name ?? ''}
        lookingAt={[...(selectedTrack ? [selectedTrack.display_name || say.detail.contact] : []), ...zoneNames.slice(0, 2)]}
        collapsed={assistantAway}
        onToggle={() => setAssistantAway(!assistantAway)}
        onProposal={setProposalPath}
        onOrdered={() => setNotice('')}
      />
    </div>
  )
}

/* ------------------------------ the fleet ------------------------------ */

/** A machine's class, in the letters an operator uses. Unknown reads as itself. */
function classLabel(assetClass: string | undefined): string {
  if (!assetClass) return ''
  const known: Record<string, string> = { ugv: 'UGV', uav: 'UAV', usv: 'USV', uuv: 'UUV' }
  return known[assetClass.toLowerCase()] ?? plain(assetClass)
}

function FleetRail({
  world,
  machines,
  contacts,
  now,
  answering,
  classFilter,
  onClassFilter,
  selectedAssetId,
  selectedTrackId,
  onSelectAsset,
  onSelectTrack,
}: {
  world: World
  machines: Asset[]
  contacts: Track[]
  now: number
  answering: (assetId: string) => boolean
  classFilter: string
  onClassFilter: (c: string) => void
  selectedAssetId: string | null
  selectedTrackId: string | null
  onSelectAsset: (id: string) => void
  onSelectTrack: (id: string) => void
}) {
  const [allOrders, setAllOrders] = useState(false)
  const [allAlerts, setAllAlerts] = useState(false)
  const classes = useMemo(
    () => [...new Set(machines.map((m) => (m.asset_class ?? '').toLowerCase()).filter(Boolean))],
    [machines],
  )
  const shown = classFilter ? machines.filter((m) => (m.asset_class ?? '').toLowerCase() === classFilter) : machines
  const orders = useMemo(() => sortedTasks([...world.tasks.values()]), [world.tasks])
  const alerts = useMemo(() => world.events.filter((e) => severityStatus(e.severity) !== 'ok'), [world.events])

  return (
    <aside className="col-left">
      <section className="stack">
        <div className="stack-head">
          <span className="title">{say.operate.fleet}</span>
          <span className="lbtn is-inert" title={say.notBuiltYet}>
            {say.operate.addMachine}
          </span>
        </div>
        {classes.length > 1 && (
          <div className="segments" role="group">
            <button className={classFilter === '' ? 'on' : ''} onClick={() => onClassFilter('')}>
              {say.operate.all} {machines.length}
            </button>
            {classes.map((c) => (
              <button key={c} className={classFilter === c ? 'on' : ''} onClick={() => onClassFilter(c)}>
                {classLabel(c)} {machines.filter((m) => (m.asset_class ?? '').toLowerCase() === c).length}
              </button>
            ))}
          </div>
        )}
        {shown.length === 0 && <p className="empty">{say.rails.noMachines}</p>}
        {shown.map((machine) => (
          <MachineCard
            key={machine.asset_id}
            machine={machine}
            world={world}
            now={now}
            answering={answering(machine.asset_id)}
            selected={machine.asset_id === selectedAssetId}
            onSelect={() => onSelectAsset(machine.asset_id)}
          />
        ))}
      </section>

      <section className="stack">
        <div className="stack-head">
          <span className="h">{say.operate.orders}</span>
          {orders.length > 2 && (
            <button className="link" onClick={() => setAllOrders(!allOrders)}>
              {allOrders ? say.operate.fewer : say.operate.viewAll}
            </button>
          )}
        </div>
        {orders.length === 0 && <p className="empty">{say.operate.noOrders}</p>}
        {(allOrders ? orders : orders.slice(0, 2)).map((task) => (
          <OrderCard key={task.task_id} task={task} world={world} />
        ))}
      </section>

      <section className="stack">
        <div className="stack-head">
          <span className="h">{say.operate.alerts}</span>
          {alerts.length > 3 && (
            <button className="link" onClick={() => setAllAlerts(!allAlerts)}>
              {allAlerts ? say.operate.fewer : say.operate.viewAll}
            </button>
          )}
        </div>
        <div className="card list">
          {alerts.length === 0 && <p className="empty">{say.operate.noAlerts}</p>}
          {(allAlerts ? alerts : alerts.slice(0, 3)).map((event) => (
            <div key={event.event_id} className="act">
              <span className={`ico is-${severityStatus(event.severity)}`} aria-hidden />
              {/* Already a plain sentence when it arrives. C2 never rewrites it. */}
              <span className="act-text">{event.text}</span>
              <span className="act-ago">{agoInWords(now - event.ts)}</span>
            </div>
          ))}
        </div>
      </section>

      {contacts.length > 0 && (
        <section className="stack">
          <div className="stack-head">
            <span className="h">{say.rails.contacts}</span>
          </div>
          {contacts.map((contact) => (
            <ContactRow
              key={contact.track_id}
              contact={contact}
              world={world}
              now={now}
              selected={contact.track_id === selectedTrackId}
              onSelect={() => onSelectTrack(contact.track_id)}
            />
          ))}
        </section>
      )}
    </aside>
  )
}

const OPEN_STATES = new Set(['TASK_STATE_PENDING', 'TASK_STATE_ACCEPTED', 'TASK_STATE_RUNNING'])

function taskTime(task: Task): number {
  const history = task.status_history ?? []
  const last = history[history.length - 1]?.timestamp
  return last ? Date.parse(last) / 1000 : 0
}

/** Open orders first, then the most recently changed. */
function sortedTasks(tasks: Task[]): Task[] {
  return tasks.sort((a, b) => {
    const openA = OPEN_STATES.has(a.status ?? '') ? 1 : 0
    const openB = OPEN_STATES.has(b.status ?? '') ? 1 : 0
    return openB - openA || taskTime(b) - taskTime(a)
  })
}

/** An order's state in words. Anything unknown reads as itself. */
function taskStateInWords(status: string | undefined): { text: string; status: Status } {
  const rest = (status ?? '').replace(/^TASK_STATE_/, '')
  const text = say.operate.taskState[rest] ?? (rest ? plain(rest) : '')
  const tone: Status =
    rest === 'DONE' ? 'ok' : rest === 'FAILED' ? 'act' : rest === 'CANCELLED' ? 'off' : rest === 'RUNNING' ? 'ok' : 'warn'
  return { text, status: tone }
}

function OrderCard({ task, world }: { task: Task; world: World }) {
  const state = taskStateInWords(task.status)
  const machine = world.assets.get(task.asset_id)?.display_name ?? ''
  const at = taskTime(task)
  return (
    <div className={`card order${OPEN_STATES.has(task.status ?? '') ? ' is-open' : ''}`}>
      <div className="order-top">
        <strong>{orderInWords(task)}</strong>
        <span className={`pill is-${state.status} is-small`}>{state.text}</span>
      </div>
      <span className="sub">
        {[machine, task.ordered_by, at ? clockAt(at) : ''].filter(Boolean).join(' · ')}
      </span>
    </div>
  )
}

function MachineCard({
  machine,
  world,
  now,
  answering,
  selected,
  onSelect,
}: {
  machine: Asset
  world: World
  now: number
  answering: boolean
  selected: boolean
  onSelect: () => void
}) {
  const status = assetStatus(machine.status, answering)
  const battery = machine.battery_fraction
  const heard = lastHeardAt(world, machine)
  return (
    <button className={`vcard${selected ? ' sel' : ''}`} onClick={onSelect} aria-pressed={selected}>
      <span className="thumb" aria-hidden>
        <VehicleGlyph />
      </span>
      <span className="vbody">
        <span className="vname">{machine.display_name}</span>
        <span className="vtype">{classLabel(machine.asset_class)}</span>
        <span className={`vstate is-${status}`}>
          <span className="dot" />
          {statusInWords(machine.status, answering)}
        </span>
      </span>
      <span className="vright">
        {battery !== undefined &&
          (answering ? (
            <span className="batt">
              <span className="battbox">
                <span
                  className={`battfill is-${battery < 0.15 ? 'act' : battery < 0.3 ? 'warn' : 'ok'}`}
                  style={{ width: `${Math.round(battery * 100)}%` }}
                />
              </span>
              {Math.round(battery * 100)}%
            </span>
          ) : (
            // A reading from a machine we cannot hear is a reading from the
            // past, and is said so.
            <span className="batt was">{say.machine.batteryWas(Math.round(battery * 100))}</span>
          ))}
      </span>
      {!answering && (
        <span className="vnote">
          {/* Two separate facts: when we last heard, and whether there is
              anything on the map to caveat. */}
          {`${heard ? `${say.map.lastHeard} ${agoInWords(now - heard)}` : say.map.notHeard}. ${
            positionOf(world, machine) ? say.machine.stale : say.machine.neverReported
          }`}
        </span>
      )}
    </button>
  )
}

function ContactRow({
  contact,
  world,
  now,
  selected,
  onSelect,
}: {
  contact: Track
  world: World
  now: number
  selected: boolean
  onSelect: () => void
}) {
  const lastSeen = lastSeenSeconds(contact, now)
  const seenBy = observersOf(contact, world)
  const line = [
    contact.place ? `${contact.place}.` : '',
    seenBy ? say.detail.seenByAgo(seenBy, agoInWords(lastSeen)) : `${say.detail.lastSeen} ${agoInWords(lastSeen)}.`,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <button className={`vcard is-contact${selected ? ' sel' : ''}`} onClick={onSelect}>
      <span className="diamond" />
      <span className="vbody">
        {/* Named by the server, hedge included. C2 never composes this. */}
        <span className="vname">{contact.display_name || say.detail.contact}</span>
        <span className="vnote">{line}</span>
      </span>
      <span className="vstate is-warn">{confidenceInWords(contact.confidence)}</span>
    </button>
  )
}

/* ----------------------------- the centre ------------------------------ */

function CameraCard({ machine, systems }: { machine: Asset | null; systems: SystemsView | null }) {
  const camera = systems?.cameras[0]
  return (
    <div className="card camera-card">
      <div className="card-head">
        <span className="h">{machine?.display_name ?? ''}</span>
        {machine && <span className="sep">·</span>}
        <span className="card-sub">{camera ? camera.name : say.operate.camera.front}</span>
        <span className={`pill is-off is-small right`}>
          <span className="dot" />
          {camera ? say.operate.camera.noVideo : say.operate.camera.noCamera}
        </span>
      </div>
      <div className="video-tile">
        <CameraGlyph />
        <span>
          {!machine
            ? say.operate.noneSelected
            : camera
              ? `${camera.text} ${say.operate.camera.videoLater}`
              : say.operate.camera.noCameraText(machine.display_name)}
        </span>
      </div>
    </div>
  )
}

function ReadingsCard({
  machine,
  world,
  now,
  answering,
  systems,
  mode,
  task,
  onMode,
  onStop,
}: {
  machine: Asset | null
  world: World
  now: number
  answering: boolean
  systems: SystemsView | null
  mode: Mode
  task: Task | undefined
  onMode: (m: Mode) => void
  onStop: () => void
}) {
  const live = machine ? world.telemetry.get(machine.asset_id) : undefined
  const heard = machine ? lastHeardAt(world, machine) : undefined
  const battery = machine?.battery_fraction
  const latest = useMemo(() => {
    const history = task?.status_history ?? []
    for (let i = history.length - 1; i >= 0; i--) if (history[i]?.message) return history[i].message
    return undefined
  }, [task])
  const orderState = task ? taskStateInWords(task.status) : null

  return (
    <div className="card readings-card">
      <div className="card-head">
        <span className="h">{machine?.display_name ?? ''}</span>
        {machine && <span className="sep">·</span>}
        <span className="card-sub">{say.operate.readings.title}</span>
        {machine && (
          <span className={`pill is-${answering ? 'ok' : 'off'} is-small right`}>
            <span className="dot" />
            {answering ? say.operate.readings.live : say.operate.readings.quiet}
          </span>
        )}
      </div>
      {!machine ? (
        <p className="empty">{say.operate.noneSelected}</p>
      ) : (
        <>
          <div className="stats">
            <div className="stat">
              <span className={`v${answering ? '' : ' was'}`}>
                {live?.speed_mps !== undefined ? live.speed_mps.toFixed(1) : '·'}
                <span>m/s</span>
              </span>
              <span className="k">{say.operate.readings.speed}</span>
            </div>
            <div className="stat">
              <span className={`v${answering ? '' : ' was'}`}>
                {battery !== undefined ? Math.round(battery * 100) : '·'}
                <span>%</span>
              </span>
              <span className="k">{say.operate.readings.battery}</span>
            </div>
            <div className="stat">
              <span className={`v is-text ${answering ? 'is-ok' : 'is-off'}`}>
                {answering ? say.operate.readings.good : say.machine.notAnswering}
                <span>
                  {heard ? say.operate.readings.heard(agoInWords(now - heard)) : say.map.notHeard}
                </span>
              </span>
              <span className="k">{say.operate.readings.link}</span>
            </div>
            <div className="stat">
              <span className="v is-text is-off">{systems?.position_source ?? say.operate.readings.unverified}</span>
              <span className="k">{say.operate.readings.positionSource}</span>
            </div>
          </div>

          <div className="order-row">
            <span className="order-label">{say.operate.readings.currentOrder}</span>
            {mode && <span className="plan-mode">{modeInWords(mode)}</span>}
            <span className={`pill is-${orderState ? orderState.status : 'off'} is-small right`}>
              {orderState ? orderState.text : say.operate.readings.nothingOrdered}
            </span>
          </div>
          <p className="order-line">
            {task ? (
              <>
                {orderInWords(task)}
                {task.reason ? `, ${task.reason}` : ''}
                {latest ? `. ${latest}` : '.'}
                {mode === 'manual' ? ` ${say.mode.manualAssurance}` : ''}
                {mode === 'automatic' ? ` ${say.mode.automaticAssurance}` : ''}
              </>
            ) : mode === 'automatic' ? (
              say.mode.automaticMeans
            ) : mode === 'manual' ? (
              say.plan.nothing
            ) : (
              say.plan.nothingFor
            )}
          </p>

          <div className="order-actions">
            <div className="segmented" role="group">
              {(['manual', 'automatic'] as const).map((option) => (
                <button
                  key={option}
                  className={mode === option ? 'on' : ''}
                  onClick={() => onMode(option)}
                  title={option === 'manual' ? say.mode.manualMeans : say.mode.automaticMeans}
                >
                  <span className="pip" />
                  {option === 'manual' ? say.mode.manual : say.mode.automatic}
                </button>
              ))}
            </div>
            {task && (
              <button className="mini stop" onClick={onStop}>
                {say.plan.stop}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function ActivityCard({ events }: { events: WorldEvent[] }) {
  const [all, setAll] = useState(false)
  const shown = all ? events : events.slice(0, 6)
  return (
    <div className="card activity-card">
      <div className="card-head">
        <span className="h">{say.operate.activity}</span>
        {events.length > 6 && (
          <button className="link right" onClick={() => setAll(!all)}>
            {all ? say.operate.fewer : say.operate.viewAll}
          </button>
        )}
      </div>
      <div className="activity">
        {events.length === 0 && <p className="empty">{say.rails.noEvents}</p>}
        {shown.map((event) => (
          <div key={event.event_id} className="act">
            <span className={`ico is-${severityStatus(event.severity)}`} aria-hidden />
            <time>{clockAt(event.ts)}</time>
            <span className="act-text">{event.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function CamerasCard({ machine, systems }: { machine: Asset | null; systems: SystemsView | null }) {
  const cameras = systems?.cameras ?? []
  return (
    <div className="card cameras-card">
      <div className="card-head">
        <span className="h">{say.operate.cameras}</span>
      </div>
      {cameras.length > 0 ? (
        <>
          <div className="cams">
            {cameras.map((camera) => (
              <div key={camera.name} className="cam">
                <span className={`cam-tile is-${camera.state}`}>
                  <CameraGlyph small />
                </span>
                <span>{camera.name}</span>
              </div>
            ))}
          </div>
          <span className="sub">{cameras.map((c) => c.text).join(' ')}</span>
        </>
      ) : (
        <p className="empty">{machine ? say.operate.camera.noCameraText(machine.display_name) : say.operate.noneSelected}</p>
      )}
    </div>
  )
}

function SystemsCard({ machine, systems }: { machine: Asset | null; systems: SystemsView | null }) {
  return (
    <div className="card systems-card">
      <div className="card-head">
        <span className="h">{say.operate.systems}</span>
      </div>
      {!machine ? (
        <p className="empty">{say.operate.noneSelected}</p>
      ) : !systems ? (
        <p className="empty">{say.operate.asking}</p>
      ) : (
        <>
          {systems.rows.map((row) => (
            <div key={row.name} className="sys">
              <span className={`dot is-${row.state === 'unknown' ? 'off' : row.state}`} />
              {row.name}
              <span className={`r is-${row.state === 'unknown' ? 'off' : row.state}`}>{row.text}</span>
            </div>
          ))}
          {systems.note && <span className="sub">{systems.note}</span>}
        </>
      )}
    </div>
  )
}

/* ------------------------------- helpers ------------------------------- */

/** The machines that saw a contact, in the names an operator reads. */
function observersOf(contact: Track, world: World): string {
  return (contact.contributing_asset_ids ?? [])
    .map((id) => world.assets.get(id)?.display_name)
    .filter(Boolean)
    .join(', ')
}

/**
 * What was ordered, in the server's words. The server's language file
 * already turns the task type into a sentence, and an order added after
 * this build shipped still reads as English.
 */
function orderInWords(task: { phrase?: string; task_type: string }): string {
  return task.phrase ? plain(task.phrase) : plain(task.task_type)
}

function confidenceInWords(confidence: number | undefined): string {
  const tenths = outOfTen(confidence)
  return tenths === null ? say.detail.noFigure : `${tenths} in 10`
}

function lastSeenSeconds(contact: Track, now: number): number {
  const history = contact.history ?? []
  const last = history[history.length - 1]?.timestamp
  if (!last) return 0
  return Math.max(0, now - Date.parse(last) / 1000)
}

function ContactDetail({
  contact,
  world,
  now,
  canSend,
  cannotSendWhy,
  machineName,
  onSend,
  onClose,
}: {
  contact: Track
  world: World
  now: number
  canSend: boolean
  cannotSendWhy: string
  machineName: string
  onSend: () => void
  onClose: () => void
}) {
  const tenths = outOfTen(contact.confidence)
  const seenBy = observersOf(contact, world)

  return (
    <section className="detail card">
      <header>
        <span className="diamond" />
        <h3>{contact.display_name || say.detail.contact}</h3>
        <button className="x" onClick={onClose} aria-label={say.detail.close}>
          &times;
        </button>
      </header>

      {/* The honesty law, on the screen. Never rounded up into a fact. */}
      <div className="doubt">
        <strong>{say.detail.mightBeWrong}</strong>{' '}
        {tenths === null ? say.detail.noFigure : say.detail.sureOutOfTen(tenths)}
        {tenths !== null && (
          <div className="meter">
            {Array.from({ length: 10 }, (_, i) => (
              <i key={i} className={i < tenths ? 'on' : ''} />
            ))}
          </div>
        )}
      </div>

      <dl>
        <div>
          <dt>{say.detail.seenBy}</dt>
          <dd>{seenBy || say.detail.notRecorded}</dd>
        </div>
        <div>
          <dt>{say.detail.lastSeen}</dt>
          <dd>{agoInWords(lastSeenSeconds(contact, now))}</dd>
        </div>
      </dl>

      <footer>
        <button className="btn primary" onClick={onSend} disabled={!canSend}>
          {canSend ? say.detail.sendNamed(machineName) : cannotSendWhy}
        </button>
      </footer>
    </section>
  )
}

function SearchGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-4-4" />
    </svg>
  )
}

function VehicleGlyph() {
  return (
    <svg viewBox="0 0 40 28" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 18h32v-6l-6-6H14l-6 6z" />
      <circle cx="12" cy="20" r="3.5" fill="var(--card-3)" />
      <circle cx="28" cy="20" r="3.5" fill="var(--card-3)" />
      <path d="M14 6v6h12V6" opacity="0.6" />
    </svg>
  )
}

function CameraGlyph({ small = false }: { small?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width={small ? 16 : 28} height={small ? 16 : 28}>
      <rect x="3" y="7" width="13" height="10" rx="1.5" />
      <path d="M16 10l5-2.5v9L16 14" />
    </svg>
  )
}
