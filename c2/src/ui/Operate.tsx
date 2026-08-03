/**
 * Operate: the one screen.
 *
 * Force on the left, map in the middle, what happened on the right, what
 * the machines are doing along the bottom. Nothing nests. Anything that
 * needs more room opens over the map and closes back.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { track as api, Refused } from '../sdk/client'
import type { Link } from '../sdk/stream'
import type { Asset, Track } from '../sdk/types'
import { isAnswering, openTaskFor, useContacts, useMachines, type World } from '../state/world'
import { MapView } from './MapView'
import {
  agoInWords,
  assetStatus,
  outOfTen,
  plain,
  say,
  severityStatus,
  statusInWords,
} from './wording'

type Mode = 'manual' | 'automatic'

interface Props {
  world: World
  link: Link
  theme: 'dark' | 'day'
}

export function Operate({ world, link, theme }: Props) {
  const machines = useMachines(world)
  const contacts = useContacts(world)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('manual')
  const [notice, setNotice] = useState<string>('')
  const [now, setNow] = useState(() => Date.now() / 1000)

  // One clock for the whole screen, so every "how long ago" agrees.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => window.clearInterval(timer)
  }, [])

  // Select the first machine as soon as one appears, so the screen is never
  // waiting for a click to become useful.
  useEffect(() => {
    if (selectedAssetId === null && machines.length > 0) setSelectedAssetId(machines[0].asset_id)
  }, [machines, selectedAssetId])

  const answering = useCallback(
    (assetId: string) => isAnswering(world, assetId, now, link === 'lost'),
    [world, now, link],
  )

  const selected = selectedAssetId ? world.assets.get(selectedAssetId) ?? null : null
  const selectedTrack = selectedTrackId ? world.tracks.get(selectedTrackId) ?? null : null
  const openTask = selected ? openTaskFor(world, selected.asset_id) : undefined
  const canSend = Boolean(selected && answering(selected.asset_id) && mode === 'manual')

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
   * Automatic. The machines work to their standing orders rather than
   * waiting to be told. For this build that means one standing order: go
   * and look at anything new that turns up. C2 issues it through the same
   * public endpoint an operator's click uses, and writes the channel into
   * the audit trail so it is always clear who ordered what.
   */
  const investigated = useRef<Set<string>>(new Set())
  useEffect(() => {
    if (mode !== 'automatic' || !selected || !answering(selected.asset_id)) return
    if (openTask) return
    const fresh = contacts.find(
      (c) =>
        !investigated.current.has(c.track_id) &&
        c.position?.latitude_deg !== undefined &&
        c.position?.longitude_deg !== undefined,
    )
    if (!fresh) return
    investigated.current.add(fresh.track_id)
    void send(fresh.position!.latitude_deg!, fresh.position!.longitude_deg!, 'automatic', fresh.track_id)
  }, [mode, contacts, selected, openTask, answering, send])

  const switchMode = (next: Mode) => {
    setMode(next)
    setNotice(next === 'automatic' ? say.mode.switchedToAutomatic : say.mode.switchedToManual)
    if (next === 'manual' && openTask) void stop()
  }

  return (
    <div className="operate">
      <Toolbar mode={mode} onMode={switchMode} link={link} />

      <aside className="rail rail-left">
        <SectionHeading label={say.rails.machines} count={machines.length} />
        {machines.length === 0 && <p className="empty">{say.rails.noMachines}</p>}
        {machines.map((machine) => (
          <MachineRow
            key={machine.asset_id}
            machine={machine}
            world={world}
            now={now}
            answering={answering(machine.asset_id)}
            selected={machine.asset_id === selectedAssetId}
            onSelect={() => setSelectedAssetId(machine.asset_id)}
          />
        ))}

        <SectionHeading label={say.rails.contacts} count={contacts.length} />
        {contacts.length === 0 && <p className="empty">{say.rails.noContacts}</p>}
        {contacts.map((contact) => (
          <ContactRow
            key={contact.track_id}
            contact={contact}
            now={now}
            selected={contact.track_id === selectedTrackId}
            onSelect={() => setSelectedTrackId(contact.track_id)}
          />
        ))}
      </aside>

      <div className="map-holder">
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
        />
        {canSend && <div className="map-hint">{say.map.clickToSend}</div>}
        {link === 'lost' && <div className="map-warning">{say.link.lostDetail}</div>}
        {selectedTrack && (
          <ContactDetail
            contact={selectedTrack}
            world={world}
            now={now}
            canSend={Boolean(selected && answering(selected.asset_id))}
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

      <aside className="rail rail-right">
        <SectionHeading label={say.rails.happened} />
        {world.events.length === 0 && <p className="empty">{say.rails.noEvents}</p>}
        {world.events.map((event) => (
          <article key={event.event_id} className={`event is-${severityStatus(event.severity)}`}>
            <time>{new Date(event.ts * 1000).toISOString().slice(11, 19)}</time>
            {/* Already a plain sentence when it arrives. C2 never rewrites it. */}
            <p>{event.text}</p>
            <small>{event.source}</small>
          </article>
        ))}
      </aside>

      <PlanStrip
        mode={mode}
        machine={selected}
        task={openTask}
        onStop={() => void stop()}
        onTakeControl={() => switchMode('manual')}
      />

      <div className="voicebar">
        <button className="ptt" disabled title={say.voice.notYet} aria-label={say.voice.hold}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0" />
            <line x1="12" y1="18" x2="12" y2="21" />
          </svg>
        </button>
        <p className="said">{notice || say.voice.notYet}</p>
      </div>
    </div>
  )
}

function SectionHeading({ label, count }: { label: string; count?: number }) {
  return (
    <h2 className="section">
      {label}
      {count !== undefined && <span className="count">{count}</span>}
    </h2>
  )
}

function Toolbar({ mode, onMode, link }: { mode: Mode; onMode: (m: Mode) => void; link: Link }) {
  return (
    <div className="toolbar">
      <div className="find">{say.find.placeholder}</div>
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
      {/* The site link is stated once, in the menu bar. This says only
          whether the picture on screen is moving. */}
      <div className={`live is-${link === 'good' ? 'ok' : 'warn'}`}>
        <span className="dot" />
        {link === 'good' ? say.live : say.link.connecting}
      </div>
    </div>
  )
}

function MachineRow({
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
  const live = world.telemetry.get(machine.asset_id)
  const status = assetStatus(machine.status, answering)
  const battery = machine.battery_fraction
  const task = openTaskFor(world, machine.asset_id)
  const heard = live?.timestamp

  return (
    <button className={`row ${selected ? 'is-selected' : ''}`} onClick={onSelect}>
      <div className="row-top">
        <span className={`dot is-${status}`} />
        <span className="row-name">{machine.display_name}</span>
        <span className={`row-state is-${status}`}>{statusInWords(machine.status, answering)}</span>
      </div>
      <p className="row-line">
        {answering
          ? task
            ? `${say.plan.heading}: ${orderInWords(task)}`
            : say.plan.nothingFor
          : `${say.map.lastHeard} ${heard ? agoInWords(now - heard) : say.map.someTimeAgo}. ${say.machine.stale}`}
      </p>
      <div className="row-nums">
        {battery !== undefined && (
          <span>
            <span className="bar">
              <span
                className={`fill is-${battery < 0.15 ? 'act' : battery < 0.3 ? 'warn' : 'ok'}`}
                style={{ width: `${Math.round(battery * 100)}%` }}
              />
            </span>
            {Math.round(battery * 100)}%
          </span>
        )}
        {answering && live?.speed_mps !== undefined && <span>{live.speed_mps.toFixed(1)} m/s</span>}
      </div>
    </button>
  )
}

function ContactRow({
  contact,
  now,
  selected,
  onSelect,
}: {
  contact: Track
  now: number
  selected: boolean
  onSelect: () => void
}) {
  const lastSeen = lastSeenSeconds(contact, now)
  return (
    <button className={`row ${selected ? 'is-selected' : ''}`} onClick={onSelect}>
      <div className="row-top">
        <span className="diamond" />
        <span className="row-name">{say.detail.contact}</span>
        <span className="row-state is-warn">{confidenceInWords(contact.confidence)}</span>
      </div>
      <p className="row-line">
        {say.detail.lastSeen} {agoInWords(lastSeen)}.
      </p>
    </button>
  )
}

/**
 * What was ordered, in the server's words. The task type is contract
 * vocabulary; the server's language file already turns it into a sentence,
 * and an order added after this build shipped still reads as English.
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
  machineName,
  onSend,
  onClose,
}: {
  contact: Track
  world: World
  now: number
  canSend: boolean
  machineName: string
  onSend: () => void
  onClose: () => void
}) {
  const tenths = outOfTen(contact.confidence)
  const seenBy = (contact.contributing_asset_ids ?? [])
    .map((id) => world.assets.get(id)?.display_name)
    .filter(Boolean)
    .join(', ')

  return (
    <section className="detail">
      <header>
        <span className="diamond" />
        <h3>{say.detail.contact}</h3>
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
        <button className="primary" onClick={onSend} disabled={!canSend}>
          {canSend ? say.detail.sendNamed(machineName) : say.map.cannotSend}
        </button>
      </footer>
    </section>
  )
}

function PlanStrip({
  mode,
  machine,
  task,
  onStop,
  onTakeControl,
}: {
  mode: Mode
  machine: Asset | null
  task: ReturnType<typeof openTaskFor>
  onStop: () => void
  onTakeControl: () => void
}) {
  // The latest thing the machine said about the order, in its own words.
  const latest = useMemo(() => {
    const history = task?.status_history ?? []
    for (let i = history.length - 1; i >= 0; i--) {
      if (history[i]?.message) return history[i].message
    }
    return undefined
  }, [task])

  return (
    <div className="plan">
      <span className="plan-mode">{mode === 'automatic' ? say.mode.automatic : say.mode.manual}</span>
      <div className="plan-body">
        {task && machine ? (
          <>
            <span className="step on">
              {orderInWords(task)}
              {latest ? `. ${latest}` : ''}
            </span>
            <span className="step">{machine.display_name}</span>
          </>
        ) : (
          <span className="plan-empty">
            {mode === 'automatic' ? say.mode.automaticMeans : say.plan.nothing}
          </span>
        )}
      </div>
      <div className="plan-actions">
        {task && (
          <button className="mini stop" onClick={onStop}>
            {say.plan.stop}
          </button>
        )}
        {mode === 'automatic' && (
          <button className="mini" onClick={onTakeControl}>
            {say.mode.takeControl}
          </button>
        )}
      </div>
    </div>
  )
}
