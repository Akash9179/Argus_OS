/**
 * Drive: one machine, one driver.
 *
 * Left: who is driving what, the self-test in sentences, this session, and
 * what happens if the link drops. Centre: the video (honestly empty until a
 * camera is checked) with the two loudest facts on it, safety state and
 * link latency, then the drive bar. Right: where the machine is facing, the
 * rear camera, and what Argus is watching. The assistant rail is shown and
 * plainly not built for Drive yet.
 *
 * Everything here is either the vehicle's telemetry, the daemon's session
 * facts, or this cockpit's own command. Nothing is a placeholder that could
 * be read as a reading.
 *
 * STOP is the bridge's latched stop, sent over the link. It is not an
 * emergency stop: the only e-stop on the vehicle is the ignition key, and
 * the button says so.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  LightsIcon,
  IgnitionIcon,
  BlinkerIcon,
  HazardIcon,
  HornIcon,
  FullscreenIcon,
  FullscreenExitIcon,
  BoltIcon,
} from '../ui/icons'
import { useDriveLoop, useTelemetry, useVehicleStore } from '../state/store'
import { useGamepad } from '../input/useGamepad'
import { ControllerPanel } from './ControllerPanel'
import { useManualDrive, type DriveDir } from '../input/useManualDrive'
import { useRemoTransport } from '../transport/useRemoTransport'
import { useBridgeTransport } from '../transport/useBridgeTransport'
import { DriveConnect } from '../transport/DriveConnect'
import { useDriveActive } from '../embed/driveActive'
import { isDriveMode, getDriveKey, setDriveKey, clearDriveKey } from '../transport/auth'
import type { PreflightState, SessionFacts, Telemetry } from '../contract'
import './cockpit.css'

const STEER_MAX_DEG = 30
const clamp1 = (n: number) => Math.max(-1, Math.min(1, n))

/** The words this screen owns. Sentences about the vehicle come from the daemon. */
const say = {
  noName: 'This machine',
  noNameNote: 'No name declared. It is shown by a generic label.',
  youDrive: 'you have the wheel',
  youWatch: 'you are watching',
  notConnected: 'not connected to a vehicle',
  driving: 'Driving',
  stopped: 'Stopped',
  latched: 'Latched: stopped itself',
  local: 'Local simulation',
  beforeYouDrive: 'Before you drive',
  passed: (ok: number, n: number) => `${ok} of ${n} passed`,
  notRun: 'Not run yet',
  notRunLine: 'Runs every time ignition comes on. Turn the ignition on to run it.',
  selfTestLine: 'Runs every time ignition comes on. Arming is refused until all pass.',
  session: 'This session',
  driver: 'Driver',
  since: 'Since',
  link: 'Link',
  commands: 'Commands',
  recording: 'Recording',
  perSecond: (n: number) => `${n} per second`,
  linkGood: (ms: number) => `Good · ${ms} ms`,
  linkDown: 'Not connected',
  recOn: (t: string) => `On · ${t}`,
  recOff: 'Off',
  ifLinkDrops: 'If the link drops',
  linkDropLine: (name: string, ms: number) =>
    `${name} stops itself after ${ms} ms of silence and stays stopped. When the link returns you re-arm before it moves again.`,
  linkDropUnknown: 'The vehicle has not said what it does on link loss. Nothing is assumed.',
  frontCamera: 'Front camera',
  rearCamera: 'Rear camera',
  noVideo: 'No video yet',
  noVideoLine: 'No video yet. Video appears here once a camera on the vehicle is checked.',
  rearLine: 'No camera has been checked on the vehicle yet.',
  linkPill: (ms: number) => `Link good · ${ms} ms`,
  linkLost: 'Link down',
  steer: (deg: number, dir: string) => (deg === 0 ? 'Steer straight' : `Steer ${deg}° ${dir}`),
  headingLabel: 'Heading',
  facing: 'Facing',
  compassNote: 'Position source: unverified. The map appears once the machine reports where it is.',
  whereItIs: 'Where it is',
  watching: 'Watching with you',
  nothingSeen: 'Nothing seen',
  watchingLine: 'Argus will call out a person or vehicle in the camera view when the cameras are live. Until then it watches the map only.',
  throttle: 'Throttle',
  steerLabel: 'Steer',
  ignition: 'Ignition',
  on: 'On',
  off: 'Off',
  arm: 'ARM',
  armed: 'Armed',
  stop: 'STOP',
  stopTitle: 'Sends a latched stop over the link: zero throttle, disarmed, until you re-arm. Not an emergency stop. The only emergency stop is the ignition key on the vehicle.',
  armTitle: 'Arm the vehicle so throttle commands are obeyed. Refused until the self-test passes.',
  fullscreen: 'Full screen',
  exitFullscreen: 'Leave full screen',
  holdToTalk: 'HOLD TO TALK',
  railTip: 'The assistant is not in Drive yet. Not in this build.',
  onScreen: 'On-screen',
  dualsense: 'DualSense',
  controllerTip: 'Controller setup and test',
  lights: 'Headlights',
  left: 'Left blinker',
  rightBlink: 'Right blinker',
  hazards: 'Hazards',
  horn: 'Horn',
}

/* ----------------------------- small helpers ----------------------------- */

function mmss(totalSec: number): string {
  const m = String(Math.floor(totalSec / 60)).padStart(2, '0')
  const s = String(Math.floor(totalSec % 60)).padStart(2, '0')
  return `${m}:${s}`
}

function clock(ms: number): string {
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function compassPoint(deg: number): string {
  return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round((((deg % 360) + 360) % 360) / 45) % 8]
}

/** A count of seconds since a moment, ticking once a second. */
function useSecondsSince(startMs: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  return startMs === null ? 0 : Math.max(0, (now - startMs) / 1000)
}

/* ------------------------------- joystick ------------------------------- */
/* Game-controller analog stick: drag the knob (X = steer, Y = throttle);
   springs back to centre on release. Kept from the previous cockpit: it is
   how you drive without a gamepad. */
function Joystick({ onChange }: { onChange: (x: number, y: number) => void }) {
  const baseRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)
  const rafRef = useRef<number | null>(null)
  const posRef = useRef({ x: 0, y: 0 })
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const dim = 72
  const TRAVEL = dim * 0.3
  const knob = Math.round(dim * 0.41)

  const set = (x: number, y: number) => {
    posRef.current = { x, y }
    setPos({ x, y })
    onChange(x, y)
  }
  const moveFrom = (clientX: number, clientY: number) => {
    const el = baseRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const rad = r.width / 2
    let dx = (clientX - (r.left + rad)) / rad
    let dy = (clientY - (r.top + rad)) / rad
    const m = Math.hypot(dx, dy)
    if (m > 1) {
      dx /= m
      dy /= m
    }
    set(clamp1(dx), clamp1(-dy))
  }
  const onDown = (e: React.PointerEvent) => {
    draggingRef.current = true
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    e.currentTarget.setPointerCapture(e.pointerId)
    moveFrom(e.clientX, e.clientY)
  }
  const onMove = (e: React.PointerEvent) => {
    if (draggingRef.current) moveFrom(e.clientX, e.clientY)
  }
  const onUp = () => {
    draggingRef.current = false
    const spring = () => {
      const p = posRef.current
      const nx = Math.abs(p.x) < 0.005 ? 0 : p.x * 0.74
      const ny = Math.abs(p.y) < 0.005 ? 0 : p.y * 0.74
      set(nx, ny)
      if (nx !== 0 || ny !== 0) rafRef.current = requestAnimationFrame(spring)
      else rafRef.current = null
    }
    rafRef.current = requestAnimationFrame(spring)
  }
  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
  }, [])

  return (
    <div
      ref={baseRef}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      role="slider"
      aria-label="Drive joystick"
      aria-valuetext={`steer ${Math.round(pos.x * STEER_MAX_DEG)} degrees, throttle ${Math.round(Math.max(0, pos.y) * 100)} percent`}
      style={{ width: dim, height: dim, position: 'relative', borderRadius: '50%', border: '1px solid var(--line-2)', background: 'var(--card-2)', touchAction: 'none', cursor: 'grab', flex: 'none' }}
    >
      <div style={{ position: 'absolute', left: '50%', top: 8, bottom: 8, width: 1, background: 'var(--line)', transform: 'translateX(-50%)' }} />
      <div style={{ position: 'absolute', top: '50%', left: 8, right: 8, height: 1, background: 'var(--line)', transform: 'translateY(-50%)' }} />
      <div
        style={{
          position: 'absolute', left: '50%', top: '50%', width: knob, height: knob, borderRadius: '50%',
          border: '1px solid var(--sel)', background: 'var(--sel-bg)', display: 'grid', placeItems: 'center',
          transform: `translate(calc(-50% + ${pos.x * TRAVEL}px), calc(-50% + ${-pos.y * TRAVEL}px))`,
        }}
      >
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--sel)' }} />
      </div>
    </div>
  )
}

/* ------------------------ hold-to-act arrow pad ------------------------ */
function HoldKey({ dir, press, release, title, children }: { dir: DriveDir; press: (d: DriveDir) => void; release: (d: DriveDir) => void; title: string; children: ReactNode }) {
  const start = (e: React.PointerEvent) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    press(dir)
  }
  const end = () => release(dir)
  return (
    <button type="button" className="lbtn" title={title} onPointerDown={start} onPointerUp={end} onPointerLeave={end} onPointerCancel={end} style={{ width: 36, height: 36, fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 600 }}>
      {children}
    </button>
  )
}

function ArrowPad({ press, release }: { press: (d: DriveDir) => void; release: (d: DriveDir) => void }) {
  return (
    <div className="row" style={{ gap: 6 }} title="Keyboard arrows also work">
      <HoldKey dir="left" press={press} release={release} title="Steer left (left arrow)">◄</HoldKey>
      <HoldKey dir="up" press={press} release={release} title="Accelerate (up arrow)"><BoltIcon width={14} height={14} /></HoldKey>
      <HoldKey dir="down" press={press} release={release} title="Brake (down arrow)">■</HoldKey>
      <HoldKey dir="right" press={press} release={release} title="Steer right (right arrow)">►</HoldKey>
    </div>
  )
}

/* ------------------------------- the cards ------------------------------- */

function safetyTone(state: Telemetry['safetyState']): { text: string; tone: 'ok' | 'warn' | 'act' } {
  if (state === 'DRIVING') return { text: say.driving, tone: 'ok' }
  if (state === 'STOPPED') return { text: say.stopped, tone: 'warn' }
  return { text: say.latched, tone: 'act' }
}

function MachineCard({ tele, session, remote }: { tele: Telemetry; session: SessionFacts | null; remote: boolean }) {
  const name = session?.vehicle ?? say.noName
  const safety = safetyTone(tele.safetyState)
  const battery = tele.battery.percent
  return (
    <div className={`vcard${remote ? '' : ' is-quiet'}`}>
      <span className="thumb" aria-hidden>
        <svg viewBox="0 0 40 28" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M4 18h32v-6l-6-6H14l-6 6z" />
          <circle cx="12" cy="20" r="3.5" fill="var(--card-3)" />
          <circle cx="28" cy="20" r="3.5" fill="var(--card-3)" />
        </svg>
      </span>
      <span className="vbody">
        <span className="vname">{name}</span>
        <span className="vtype">
          {/* No vehicle class is shown: the daemon does not report one, and the cockpit asserts nothing it was not told. */}
          {!remote ? say.notConnected : session?.role === 'DRIVER' ? say.youDrive : say.youWatch}
        </span>
        <span className={`vstate is-${remote ? safety.tone : 'off'}`}>
          <span className="dot" />
          {remote ? safety.text : say.local}
        </span>
      </span>
      {remote && (
        <span className="batt">
          <span className="battbox">
            <span className={`battfill is-${battery < 15 ? 'act' : battery < 30 ? 'warn' : 'ok'}`} style={{ width: `${battery}%` }} />
          </span>
          {battery}%
        </span>
      )}
      {remote && session && !session.vehicle && <span className="sub" style={{ flexBasis: '100%' }}>{say.noNameNote}</span>}
    </div>
  )
}

function SelfTestCard({ preflight, remote }: { preflight: PreflightState; remote: boolean }) {
  const ok = preflight.checks.filter((c) => c.ok).length
  const n = preflight.checks.length
  const ran = remote && preflight.ran
  return (
    <div className="card pad">
      <div className="row">
        <span className="h">{say.beforeYouDrive}</span>
        <span className={`pill right is-${!ran ? 'off' : preflight.pass ? 'ok' : 'act'}`}>{ran ? say.passed(ok, n) : say.notRun}</span>
      </div>
      {ran &&
        preflight.checks.map((check) => (
          <div key={check.name} className="chk">
            <span className={`ico is-${check.ok ? 'ok' : 'act'}`} aria-hidden />
            <div>
              {/* The daemon's sentence; an older daemon's bare name is shown as itself. */}
              <span>{check.label ?? check.name.replace(/_/g, ' ')}</span>
              <small>{check.detail}</small>
            </div>
          </div>
        ))}
      <span className="sub">{ran ? say.selfTestLine : say.notRunLine}</span>
    </div>
  )
}

function SessionCard({ tele, session, remote, hz, linkOpen }: { tele: Telemetry; session: SessionFacts | null; remote: boolean; hz: number; linkOpen: boolean }) {
  const since = useSecondsSince(session?.since ?? null)
  const rec = useSecondsSince(useVehicleStore((s) => s.recordingSince))
  return (
    <div className="card pad">
      <span className="h">{say.session}</span>
      <div className="kv">
        <span className="k">{say.driver}</span>
        <span className="v">{session?.driver || (remote ? '' : say.notConnected)}</span>
        <span className="k">{say.since}</span>
        <span className="v">{session ? `${clock(session.since)} · ${Math.floor(since / 60)} min` : ''}</span>
        <span className="k">{say.link}</span>
        <span className={`v ${linkOpen ? 'is-ok' : 'is-off'}`}>{linkOpen ? say.linkGood(tele.linkRttMs) : say.linkDown}</span>
        <span className="k">{say.commands}</span>
        <span className="v">{linkOpen ? say.perSecond(hz) : ''}</span>
        <span className="k">{say.recording}</span>
        <span className={`v ${tele.recording ? 'is-act' : ''}`}>{remote ? (tele.recording ? say.recOn(mmss(rec)) : say.recOff) : ''}</span>
      </div>
    </div>
  )
}

function LinkLossCard({ session }: { session: SessionFacts | null }) {
  return (
    <div className="card pad" style={{ marginTop: 'auto' }}>
      <span className="h">{say.ifLinkDrops}</span>
      <span className="line">
        {session?.watchdogMs != null ? say.linkDropLine(session.vehicle ?? say.noName, session.watchdogMs) : say.linkDropUnknown}
      </span>
    </div>
  )
}

function SteerArc({ steer }: { steer: number }) {
  // A short arc that bends the way the wheels point.
  const s = clamp1(steer)
  const cx = 60 + s * 26
  return (
    <svg className="steer-arc" viewBox="0 0 120 34" fill="none" aria-hidden>
      <path d="M12 30 Q60 -8 108 30" stroke="var(--line-2)" strokeWidth="2" />
      <path d={`M60 30 Q${60 + s * 12} 12 ${cx} 6`} stroke="var(--sel)" strokeWidth="3" strokeLinecap="round" />
      <circle cx={cx} cy="6" r="4" fill="var(--sel)" />
    </svg>
  )
}

function Video({ tele, session, remote, linkOpen, onToggleRecord, fullscreen, onFullscreen }: { tele: Telemetry; session: SessionFacts | null; remote: boolean; linkOpen: boolean; onToggleRecord: () => void; fullscreen: boolean; onFullscreen: () => void }) {
  const name = session?.vehicle ?? say.noName
  const safety = safetyTone(tele.safetyState)
  const steerDeg = Math.round(Math.abs(tele.steerAngleDeg))
  const dir = tele.steerAngleDeg < 0 ? 'left' : 'right'
  const rec = useSecondsSince(useVehicleStore((s) => s.recordingSince))
  return (
    <div className="card video">
      <div className="video-ground" />
      <div className="video-horizon" />
      <div className="video-empty">
        <div>
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--ink-3)" strokeWidth="1.6">
            <rect x="3" y="7" width="13" height="10" rx="1.5" />
            <path d="M16 10l5-2.5v9L16 14" />
          </svg>
          <span>{say.noVideoLine}</span>
        </div>
      </div>

      <div className="hud-tl">
        <button type="button" className={`rec ${tele.recording ? 'is-on' : 'is-off'}`} onClick={onToggleRecord} title={tele.recording ? 'Stop recording' : 'Start recording'}>
          <span className="dot" />
          REC{tele.recording ? ` ${mmss(rec)}` : ''}
        </button>
        <span className="hud-cam">
          {name} · {say.frontCamera}
        </span>
      </div>
      <div className="hud-tr">
        {remote && <span className={`pill ${linkOpen ? 'is-ok' : 'is-act'}`}><span className="dot" />{linkOpen ? say.linkPill(tele.linkRttMs) : say.linkLost}</span>}
        {remote && <span className={`pill is-loud is-${safety.tone}`}>{safety.text.toUpperCase()}</span>}
        <button type="button" className="hud-btn" onClick={onFullscreen} title={fullscreen ? say.exitFullscreen : say.fullscreen} aria-label={fullscreen ? say.exitFullscreen : say.fullscreen}>
          {fullscreen ? <FullscreenExitIcon width={14} height={14} /> : <FullscreenIcon width={14} height={14} />}
        </button>
      </div>

      <div className="hud-bl">
        <span className="speed">{tele.speedKmh.toFixed(1)}</span>
        <span className="speed-unit">km/h</span>
        <span className="gear-hud">{tele.gear === 'F' ? 'D' : tele.gear}</span>
      </div>
      <div className="hud-bc">
        <SteerArc steer={tele.steerAngleDeg / STEER_MAX_DEG} />
        <span className="hud-small">{say.steer(steerDeg, dir)}</span>
      </div>
      <div className="hud-br">
        <span className="heading">
          {compassPoint(tele.headingDeg)}
          <small>{Math.round(tele.headingDeg)}°</small>
        </span>
        <span className="hud-k">{say.headingLabel}</span>
      </div>
    </div>
  )
}

function DriveBar({ tele, padConnected, onStick, onOpenController, manual, remote }: { tele: Telemetry; padConnected: boolean; onStick: (x: number, y: number) => void; onOpenController: () => void; manual: { press: (d: DriveDir) => void; release: (d: DriveDir) => void }; remote: boolean }) {
  const command = useVehicleStore((s) => s.command)
  const setGear = useVehicleStore((s) => s.setGear)
  const toggleIgnition = useVehicleStore((s) => s.toggleIgnition)
  const toggleHeadlights = useVehicleStore((s) => s.toggleHeadlights)
  const setBlinker = useVehicleStore((s) => s.setBlinker)
  const toggleHorn = useVehicleStore((s) => s.toggleHorn)
  const estop = useVehicleStore((s) => s.estop)
  const arm = useVehicleStore((s) => s.arm)
  const preflight = useVehicleStore((s) => s.preflight)
  const driving = tele.safetyState === 'DRIVING'
  const blinker = tele.lights.blinker
  const canArm = !driving && (!remote || (preflight.ran && preflight.pass))

  return (
    <div className="card drivebar">
      <div className="gears" role="group" aria-label="Gear">
        {(['R', 'N', 'F'] as const).map((g) => (
          <button key={g} type="button" className={tele.gear === g ? 'on' : ''} onClick={() => setGear(g)} aria-pressed={tele.gear === g}>
            {g === 'F' ? 'D' : g}
          </button>
        ))}
      </div>

      <div className="bars">
        <div className="bar-row">
          <span>{say.throttle}</span>
          <span className="bar"><span className="bar-fill" style={{ width: `${Math.round(command.throttle * 100)}%` }} /></span>
          <span className="num">{Math.round(command.throttle * 100)}%</span>
        </div>
        <div className="bar-row">
          <span>{say.steerLabel}</span>
          <span className="bar"><span className="bar-mid" /><span className="bar-knob" style={{ left: `${50 + command.steer * 50}%` }} /></span>
          <span className="num">{Math.round(Math.abs(command.steer) * STEER_MAX_DEG)}° {command.steer < -0.02 ? 'L' : command.steer > 0.02 ? 'R' : ''}</span>
        </div>
      </div>

      <div className="inputs">
        <Joystick onChange={onStick} />
        {!padConnected && <ArrowPad press={manual.press} release={manual.release} />}
        <button type="button" className="input-tag" onClick={onOpenController} title={say.controllerTip}>
          <span className={`dot${padConnected ? ' is-ok' : ''}`} />
          {padConnected ? say.dualsense : say.onScreen}
        </button>
      </div>

      <div className="aux" role="group" aria-label="Lights and horn">
        <button type="button" className={`lbtn${tele.lights.headlights ? ' on' : ''}`} title={say.lights} aria-pressed={tele.lights.headlights} onClick={toggleHeadlights}><LightsIcon /></button>
        <button type="button" className={`lbtn${blinker === 'left' || blinker === 'hazard' ? ' on' : ''}`} title={say.left} onClick={() => setBlinker(blinker === 'left' ? 'off' : 'left')}><BlinkerIcon style={{ transform: 'scaleX(-1)' }} /></button>
        <button type="button" className={`lbtn${blinker === 'right' || blinker === 'hazard' ? ' on' : ''}`} title={say.rightBlink} onClick={() => setBlinker(blinker === 'right' ? 'off' : 'right')}><BlinkerIcon /></button>
        <button type="button" className={`lbtn${blinker === 'hazard' ? ' on is-act' : ''}`} title={say.hazards} onClick={() => setBlinker(blinker === 'hazard' ? 'off' : 'hazard')}><HazardIcon /></button>
        <button type="button" className={`lbtn${tele.lights.horn ? ' on' : ''}`} title={say.horn} onClick={toggleHorn}><HornIcon /></button>
      </div>

      <div className="safety">
        <div className="ign">
          <span>{say.ignition}</span>
          <button type="button" className={`pill ${tele.ignition ? 'is-ok' : ''}`} onClick={toggleIgnition} aria-pressed={tele.ignition} title={tele.ignition ? 'Ignition on. Press to switch off.' : 'Ignition off. Press to switch on; the self-test runs.'}>
            <IgnitionIcon width={12} height={12} /> {tele.ignition ? say.on : say.off}
          </button>
        </div>
        {driving ? (
          <span className="btn is-tall is-sel" aria-live="polite">{say.armed}</span>
        ) : (
          <button type="button" className="btn is-tall is-primary" onClick={arm} disabled={!canArm} title={say.armTitle}>
            {say.arm}
          </button>
        )}
        <button type="button" className="btn is-stop" onClick={estop} title={say.stopTitle} aria-label={`${say.stop}. ${say.stopTitle}`}>
          {say.stop}
        </button>
      </div>
    </div>
  )
}

function CompassCard({ tele, remote }: { tele: Telemetry; remote: boolean }) {
  const deg = tele.headingDeg
  return (
    <div className="card compass">
      <div className="compass-tag">
        <span className="pill is-sel">{say.whereItIs}</span>
        {remote && <span className="hud-k" style={{ color: 'var(--ink-2)' }}>{say.facing} {compassPoint(deg)}</span>}
      </div>
      <svg viewBox="0 0 100 100" aria-hidden>
        <circle cx="50" cy="50" r="44" fill="var(--card-2)" stroke="var(--line-2)" />
        {['N', 'E', 'S', 'W'].map((p, i) => (
          <text key={p} x={50 + 38 * Math.sin((i * Math.PI) / 2)} y={50 - 38 * Math.cos((i * Math.PI) / 2) + 4} textAnchor="middle" fontSize="9" fill="var(--ink-3)" fontFamily="var(--sans)">{p}</text>
        ))}
        <g transform={`rotate(${remote ? deg : 0} 50 50)`}>
          <polygon points="50,18 56,52 50,46 44,52" fill={remote ? 'var(--sel)' : 'var(--ink-4)'} />
        </g>
      </svg>
      <span className="compass-note">{say.compassNote}</span>
    </div>
  )
}

/* ------------------------------- the screen ------------------------------- */

export function CockpitScreen() {
  useDriveLoop()
  const [driveKey, setDriveKeyState] = useState<string | null>(() => getDriveKey())
  const [entered, setEntered] = useState(false)
  const showConnect = isDriveMode() && !entered
  // Embedded in C2, Drive commands only while it is the active screen.
  const driveActive = useDriveActive()
  const remo = useRemoTransport(driveKey, entered, { active: driveActive })
  const bridge = useBridgeTransport(driveKey, entered, { active: driveActive })
  const link = bridge.active ? bridge : remo
  const pad = useGamepad()
  // keyboard arrows and the on-screen pad drive only when no gamepad and the cockpit is shown
  const manual = useManualDrive(!pad.connected && !showConnect && driveActive)
  const tele = useTelemetry()
  const remote = useVehicleStore((s) => s.remote)
  const preflight = useVehicleStore((s) => s.preflight)
  const setStick = useVehicleStore((s) => s.setStick)
  const toggleRecord = useVehicleStore((s) => s.toggleRecord)
  const [controllerOpen, setControllerOpen] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const session = bridge.active ? bridge.session ?? null : null
  const linkOpen = remote && link.status === 'open'

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen?.()
    else document.documentElement.requestFullscreen?.()
  }, [])
  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', onFs)
    return () => document.removeEventListener('fullscreenchange', onFs)
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (e.key.toLowerCase() === 'f') toggleFullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleFullscreen])

  return (
    <div className="drive">
      <div className="drive-col is-scroll">
        <MachineCard tele={tele} session={session} remote={remote} />
        <SelfTestCard preflight={preflight} remote={remote} />
        <SessionCard tele={tele} session={session} remote={remote} hz={bridge.hz ?? 15} linkOpen={linkOpen} />
        <LinkLossCard session={session} />
      </div>

      <div className="drive-col">
        <Video tele={tele} session={session} remote={remote} linkOpen={linkOpen} onToggleRecord={toggleRecord} fullscreen={isFullscreen} onFullscreen={toggleFullscreen} />
        <DriveBar tele={tele} padConnected={pad.connected} onStick={setStick} onOpenController={() => setControllerOpen(true)} manual={manual} remote={remote} />
      </div>

      <div className="drive-col is-scroll">
        <CompassCard tele={tele} remote={remote} />
        <div className="card camera-card">
          <div className="row">
            <span className="h" style={{ fontSize: 13 }}>{say.rearCamera}</span>
            <span className="pill right">{say.noVideo}</span>
          </div>
          <div className="tile">{say.rearLine}</div>
        </div>
        <div className="card pad" style={{ flex: 1 }}>
          <div className="row">
            <span className="h" style={{ fontSize: 13 }}>{say.watching}</span>
            <span className="pill right">{say.nothingSeen}</span>
          </div>
          <span className="line">{say.watchingLine}</span>
        </div>
      </div>

      <div className="card argus-rail" title={say.railTip} aria-disabled>
        <span className="glyph" aria-hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="8.5" />
            <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
          </svg>
        </span>
        <span className="vert">{say.holdToTalk}</span>
      </div>

      <ControllerPanel open={controllerOpen} onClose={() => setControllerOpen(false)} />
      {showConnect && (
        <DriveConnect
          link={link}
          hasPassword={!!driveKey}
          onSetPassword={(pw) => {
            setDriveKey(pw)
            setDriveKeyState(pw)
          }}
          onClearPassword={() => {
            clearDriveKey()
            setDriveKeyState(null)
          }}
          onEnter={() => setEntered(true)}
        />
      )}
    </div>
  )
}
