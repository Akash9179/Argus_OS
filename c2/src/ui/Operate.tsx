/**
 * Operate: the one screen.
 *
 * Force on the left, map in the middle, what happened on the right, what
 * the machines are doing along the bottom. Nothing nests. Anything that
 * needs more room opens over the map and closes back.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { track as api, Refused } from '../sdk/client'
import type { Link } from '../sdk/stream'
import type { Asset, Track } from '../sdk/types'
import {
  isAnswering,
  lastHeardAt,
  openTaskFor,
  positionOf,
  useContacts,
  useMachines,
  type World,
} from '../state/world'
import { MapView } from './MapView'
import { VoiceBar } from './VoiceBar'
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
  const machines = useMachines(world)
  const contacts = useContacts(world)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string>('')
  const [now, setNow] = useState(() => Date.now() / 1000)
  // Both rails start open. A section an operator collapsed stays collapsed,
  // but nothing about the force is ever hidden by default.
  const [showMachines, setShowMachines] = useState(true)
  const [showContacts, setShowContacts] = useState(true)
  const [showEvents, setShowEvents] = useState(true)

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
  /**
   * The selected machine's mode, as the server holds it. Never local
   * state: a toggle that moved before the server agreed would be showing
   * an operator a setting that is not in force anywhere. Shown as sent,
   * so an unrecognised mode reads as itself rather than as Manual, which
   * would display a setting that is not in force and quietly re-enable
   * tasking under it.
   */
  const mode: Mode = selected?.autonomy ?? ''
  /**
   * Whether this machine can be sent somewhere from here, and if not, the
   * true reason. Computed once: three separate places used to work it out
   * for themselves and gave three different answers, including telling an
   * operator a machine was not answering when it plainly was.
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
            // that works. Naming a mode we were not told is a separate
            // question, answered below by naming none.
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

  /** Returns whether the order actually stopped, so no caller announces one that did not. */
  const stop = useCallback(async (): Promise<boolean> => {
    if (!openTask) return false
    try {
      await api.cancelTask(openTask.task_id)
      return true
    } catch (error) {
      setNotice(error instanceof Refused && error.message ? error.message : say.errors.orderFailed)
      return false
    }
  }, [openTask])

  /**
   * Ask the platform to change this machine's mode.
   *
   * Nothing is cancelled here and nothing is issued here. Switching the
   * mode is itself the act: the platform sends machines to look, and the
   * platform withdraws what it started. A station that also did those
   * things would be a second authority on a question only one thing can
   * enforce, which is what this whole change replaced.
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

  return (
    <div className="operate">
      <Toolbar mode={mode} onMode={switchMode} link={link} />

      <aside className="rail rail-left">
        <div className="filter-row">
          <div className="find">
            <SearchGlyph />
            {say.find.filter}
          </div>
          <span className="chip on">{say.find.all}</span>
        </div>

        <SectionHeading
          label={say.rails.machines}
          count={machines.length}
          open={showMachines}
          onToggle={() => setShowMachines(!showMachines)}
        />
        {showMachines && machines.length === 0 && <p className="empty">{say.rails.noMachines}</p>}
        {showMachines &&
          machines.map((machine) => (
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

        <SectionHeading
          label={say.rails.contacts}
          count={contacts.length}
          open={showContacts}
          onToggle={() => setShowContacts(!showContacts)}
        />
        {showContacts && contacts.length === 0 && <p className="empty">{say.rails.noContacts}</p>}
        {showContacts &&
          contacts.map((contact) => (
            <ContactRow
              key={contact.track_id}
              contact={contact}
              world={world}
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
        {/* A map that quietly ignores clicks teaches an operator that the
            system is unreliable, so it always states where it stands. With
            no machine selected there is nothing to state. */}
        {selected && <div className="map-hint">{sending.why}</div>}
        {link === 'lost' && <div className="map-warning">{say.link.lostDetail}</div>}
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

      <aside className="rail rail-right">
        <SectionHeading
          label={say.rails.happened}
          open={showEvents}
          onToggle={() => setShowEvents(!showEvents)}
        />
        {showEvents && world.events.length === 0 && <p className="empty">{say.rails.noEvents}</p>}
        {showEvents &&
          world.events.map((event) => (
            <article key={event.event_id} className={`event is-${severityStatus(event.severity)}`}>
              <time>{clockAt(event.ts, true)}</time>
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

      <VoiceBar notice={notice} onOrdered={() => setNotice('')} />
    </div>
  )
}

function SectionHeading({
  label,
  count,
  open,
  onToggle,
}: {
  label: string
  count?: number
  open: boolean
  onToggle: () => void
}) {
  return (
    <button className={`section ${open ? 'is-open' : ''}`} onClick={onToggle} aria-expanded={open}>
      <Chevron />
      {label}
      {count !== undefined && <span className="count">{count}</span>}
    </button>
  )
}

function Chevron() {
  return (
    <svg className="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

/**
 * The map tools. Only selection is built, so the other two are shown and
 * plainly disabled rather than hidden: an operator who cannot see that
 * measuring exists cannot ask for it, and a tool that looks live but does
 * nothing is worse than one that says it is not ready.
 */
const TOOLS = [
  { key: 'select', label: say.tools.select, built: true, path: 'M5 3l14 8-6 1.6L10 19z' },
  {
    key: 'measure',
    label: say.tools.measure,
    built: false,
    path: 'M3 15L15 3l6 6L9 21z M7.5 10.5l2 2 M11 7l2 2 M14.5 3.5l2 2',
  },
  {
    key: 'mark',
    label: say.tools.mark,
    built: false,
    path: 'M12 21s7-6.3 7-11a7 7 0 1 0-14 0c0 4.7 7 11 7 11z',
  },
] as const

function Toolbar({ mode, onMode, link }: { mode: Mode; onMode: (m: Mode) => void; link: Link }) {
  return (
    <div className="toolbar">
      <div className="tools" role="group">
        {TOOLS.map((tool) => (
          <button
            key={tool.key}
            className={`tool ${tool.built ? 'on' : 'is-inert'}`}
            title={tool.built ? tool.label : `${tool.label}. ${say.notBuiltYet}`}
            aria-label={tool.label}
            disabled={!tool.built}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
              {tool.path.split(' M').map((segment, i) => (
                <path key={i} d={i === 0 ? segment : `M${segment}`} />
              ))}
            </svg>
          </button>
        ))}
      </div>
      <div className="bar-sep" />
      <div className="find">
        <SearchGlyph />
        {say.find.placeholder}
      </div>
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

function SearchGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-4-4" />
    </svg>
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
  // Heartbeats count as being heard, not just motion samples. Reading this
  // from telemetry alone claimed a machine had gone unheard when the server
  // had in fact heard from it moments ago.
  const heard = lastHeardAt(world, machine)

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
          : // Two separate facts: when we last heard, and whether there is
            // anything on the map to caveat. They come apart, because a
            // machine can heartbeat without ever sending a position, and
            // then it draws no marker. Warning about a pin that is not
            // there invents the same "was" as claiming one for a machine
            // that never reported at all.
            `${heard ? `${say.map.lastHeard} ${agoInWords(now - heard)}` : say.map.notHeard}. ${
              positionOf(world, machine) ? say.machine.stale : say.machine.neverReported
            }`}
      </p>
      <div className="row-nums">
        {/*
          A machine we cannot hear cannot tell us its charge, so its last
          reading is stated in the past tense and without the live meter.
          A green bar beside a silent machine reads as a machine that is
          fine, which is the one thing it is not known to be.
        */}
        {battery !== undefined &&
          (answering ? (
            <span>
              <span className="bar">
                <span
                  className={`fill is-${battery < 0.15 ? 'act' : battery < 0.3 ? 'warn' : 'ok'}`}
                  style={{ width: `${Math.round(battery * 100)}%` }}
                />
              </span>
              {Math.round(battery * 100)}%
            </span>
          ) : (
            <span className="was">{say.machine.batteryWas(Math.round(battery * 100))}</span>
          ))}
        {answering && live?.speed_mps !== undefined && <span>{live.speed_mps.toFixed(1)} m/s</span>}
        {answering && live?.heading_deg !== undefined && (
          <span>{say.machine.heading(live.heading_deg)}</span>
        )}
      </div>
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

  // Where it is, then who saw it and when. Each part is left out rather than
  // guessed at: the server sends no place when the contact is in no zone we
  // know, and an observation can arrive without a machine we can name.
  const line = [
    contact.place ? `${contact.place}.` : '',
    seenBy
      ? say.detail.seenByAgo(seenBy, agoInWords(lastSeen))
      : `${say.detail.lastSeen} ${agoInWords(lastSeen)}.`,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button className={`row ${selected ? 'is-selected' : ''}`} onClick={onSelect}>
      <div className="row-top">
        <span className="diamond" />
        {/* Named by the server, hedge included. C2 never composes this. */}
        <span className="row-name">{contact.display_name || say.detail.contact}</span>
        <span className="row-state is-warn">{confidenceInWords(contact.confidence)}</span>
      </div>
      <p className="row-line">{line}</p>
    </button>
  )
}

/** The machines that saw a contact, in the names an operator reads. */
function observersOf(contact: Track, world: World): string {
  return (contact.contributing_asset_ids ?? [])
    .map((id) => world.assets.get(id)?.display_name)
    .filter(Boolean)
    .join(', ')
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
    <section className="detail">
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
        <button className="primary" onClick={onSend} disabled={!canSend}>
          {canSend ? say.detail.sendNamed(machineName) : cannotSendWhy}
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

  /**
   * Why the machine is doing this. The server composes it, because working
   * it out here would mean enumerating the channel vocabulary and deciding
   * whose order it was, and getting either wrong attributes an order to
   * somebody who never gave it. Empty when nothing honest can be said.
   */
  const reason = task?.reason ?? ''

  return (
    <div className="plan">
      {/* The mode is a machine's setting. With no machine selected, or a
          server that did not say, there is no mode to name and naming one
          would describe a machine that is not there. */}
      {machine && mode && <span className="plan-mode">{modeInWords(mode)}</span>}
      <div className="plan-body">
        {task && machine ? (
          <>
            <span className="step on">
              {orderInWords(task)}
              {reason ? `, ${reason}` : ''}
              {latest ? `. ${latest}` : '.'}
              {mode === 'manual' ? ` ${say.mode.manualAssurance}` : ''}
              {mode === 'automatic' ? ` ${say.mode.automaticAssurance}` : ''}
            </span>
            <span className="step">{machine.display_name}</span>
          </>
        ) : (
          <span className="plan-empty">
            {!machine
              ? // Nothing selected. The rails already say whether any
                // machine has connected; repeating a guess here would
                // describe a fleet this strip cannot see.
                ''
              : mode === 'automatic'
                ? say.mode.automaticMeans
                : mode === 'manual'
                  ? say.plan.nothing
                  : say.plan.nothingFor}
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
