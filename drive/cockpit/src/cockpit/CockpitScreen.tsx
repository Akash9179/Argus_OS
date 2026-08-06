import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Button } from '../ui/Button'
import { SourceTag } from '../ui/Chip'
import {
  LightsIcon,
  IgnitionIcon,
  BlinkerIcon,
  HazardIcon,
  HornIcon,
  MapIcon,
  PipIcon,
  ExpandIcon,
  FullscreenIcon,
  FullscreenExitIcon,
} from '../ui/icons'
import { LeafletMap } from './LeafletMap'
import { useDriveLoop, useTelemetry, useVehicleStore } from '../state/store'
import { useGamepad } from '../input/useGamepad'
import { ControllerPanel } from './ControllerPanel'
import { GamepadIcon, BoltIcon } from '../ui/icons'
import { useManualDrive, type DriveDir } from '../input/useManualDrive'
import { PadGlyph } from '../ui/PadGlyph'
import { Metric } from '../ui/Metric'
import { useRemoTransport, type RemoLink } from '../transport/useRemoTransport'
import { useBridgeTransport } from '../transport/useBridgeTransport'
import { DriveConnect } from '../transport/DriveConnect'
import { isDriveMode, getDriveKey, setDriveKey, clearDriveKey } from '../transport/auth'
import type { Telemetry } from '../contract'
import { BrainPanel } from './BrainPanel'
import { intentToCommand, clampDurationMs } from '../brain/driveIntent'
import { assistStep, type AssistState } from '../brain/assistLoop'
import type { DriveIntent } from '../brain/types'

const STEER_MAX_DEG = 30
const clamp1 = (n: number) => Math.max(-1, Math.min(1, n))
function steerLabel(s: number) {
  const deg = Math.round(Math.abs(s) * STEER_MAX_DEG)
  if (deg === 0) return '0°'
  return `${deg}° ${s > 0 ? 'R' : 'L'}`
}

type MapView = 'map' | 'sat'

/* ─────────────────── Projected drive path (feed) ─────────────────── */
/* Bicycle-model turn: lateral offset grows with the SQUARE of distance, so the
   corridor leaves the vehicle pointing straight ahead and sweeps into an arc
   (Waymo/Tesla-style) — not a straight bar tilting. */
function PathProjection({ steer }: { steer: number }) {
  const s = clamp1(steer)
  const N = 20
  const yBot = 101
  const yTop = 46
  const nearHalf = 17
  const farHalf = 2.6
  const BEND = 40 // how hard the arc sweeps at full lock
  const cx = (t: number) => 50 + s * BEND * t * t // t^2 ⇒ vertical at the car, curving away
  const hw = (t: number) => nearHalf + (farHalf - nearHalf) * t
  const yy = (t: number) => yBot + (yTop - yBot) * t
  const fmt = (x: number, y: number) => `${x.toFixed(2)} ${y.toFixed(2)}`

  const left: string[] = []
  const right: string[] = []
  const spine: string[] = []
  for (let i = 0; i <= N; i++) {
    const t = i / N
    const c = cx(t)
    const w = hw(t)
    const y = yy(t)
    left.push(`${i === 0 ? 'M' : 'L'} ${fmt(c - w, y)}`)
    right.push(`L ${fmt(c + w, y)}`)
    spine.push(`${i === 0 ? 'M' : 'L'} ${fmt(c, y)}`)
  }
  const corridor = left.join(' ') + ' ' + right.reverse().join(' ') + ' Z'
  const spinePath = spine.join(' ')

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden
    >
      <defs>
        <linearGradient id="argus-path" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#2E8FFF" stopOpacity="0.5" />
          <stop offset="55%" stopColor="#2E8FFF" stopOpacity="0.26" />
          <stop offset="100%" stopColor="#2E8FFF" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={corridor} fill="url(#argus-path)" />
      <path d={corridor} fill="none" stroke="#2E8FFF" strokeOpacity="0.55" strokeWidth="1.25" vectorEffect="non-scaling-stroke" />
      <path d={spinePath} fill="none" stroke="#9FD0FF" strokeOpacity="0.7" strokeWidth="1.5" strokeDasharray="5 6" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

/* ─────────────────────────── Live feed ─────────────────────────── */
function FeedScene() {
  return (
    <div className="absolute inset-0">
      <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, #0a0d12 0%, #0e1319 42%, #14161a 56%, #0c0d10 100%)' }} />
      <div className="absolute left-0 right-0" style={{ top: '46%', height: '120px', background: 'radial-gradient(60% 100% at 50% 0%, rgba(120,150,190,0.10), transparent 70%)' }} />
      <div className="absolute left-0 right-0" style={{ top: '52%', height: '1px', background: 'rgba(160,180,210,0.10)' }} />
      <div className="absolute left-1/2 -translate-x-1/2" style={{ bottom: 0, top: '52%', width: '70%', background: 'linear-gradient(180deg, rgba(70,62,52,0.0) 0%, rgba(78,68,55,0.22) 45%, rgba(96,82,64,0.40) 100%)', clipPath: 'polygon(46% 0, 54% 0, 86% 100%, 14% 100%)' }} />
      <div className="absolute left-1/2 -translate-x-1/2" style={{ bottom: 0, top: '52%', width: '70%', background: 'linear-gradient(180deg, transparent 0%, rgba(150,135,110,0.20) 100%)', clipPath: 'polygon(49.4% 0, 50.6% 0, 53% 100%, 47% 100%)' }} />
      <div className="absolute inset-0 opacity-[0.05]" style={{ backgroundImage: 'repeating-linear-gradient(0deg, #ffffff 0px, #ffffff 1px, transparent 1px, transparent 3px)' }} />
      <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-black/20" />
    </div>
  )
}

function RecordControl({ recording, onToggle }: { recording: boolean; onToggle: () => void }) {
  const [secs, setSecs] = useState(872) // ~14:32 in
  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => setSecs((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [recording])
  const mm = String(Math.floor(secs / 60)).padStart(2, '0')
  const ss = String(secs % 60).padStart(2, '0')
  return (
    <button
      type="button"
      onClick={onToggle}
      title={recording ? 'Stop recording' : 'Start recording'}
      className={`inline-flex h-6 items-center gap-1.5 rounded-chip border px-2 font-mono text-[12px] font-semibold uppercase tracking-wider transition-colors ${
        recording
          ? 'border-critical/40 bg-critical-weak text-critical hover:bg-critical/20'
          : 'border-line bg-surface-2/70 text-text-2 hover:text-text'
      }`}
    >
      {recording ? (
        <>
          <span className="argus-blink h-2 w-2 rounded-full bg-critical" />
          REC <span className="tabular-nums">{mm}:{ss}</span>
          <span className="ml-0.5 h-2.5 w-px bg-critical/40" />
          <span className="h-2 w-2 rounded-[2px] bg-critical" aria-label="stop" />
        </>
      ) : (
        <>
          <span className="h-2.5 w-2.5 rounded-full border-[1.5px] border-critical" />
          REC
        </>
      )}
    </button>
  )
}

function LiveFeed({
  steer,
  recording,
  onToggleRecord,
  children,
}: {
  steer: number
  recording: boolean
  onToggleRecord: () => void
  children?: ReactNode
}) {
  return (
    <div className="relative h-full min-h-[240px] overflow-hidden rounded-card border border-line bg-surface-inset">
      <FeedScene />
      <PathProjection steer={steer} />

      <div className="absolute left-4 top-4 flex items-center gap-3">
        <RecordControl recording={recording} onToggle={onToggleRecord} />
        <span className="font-mono text-[12px] font-medium uppercase tracking-wider text-text-2">CAM • GR-1 FWD</span>
      </div>

      {/* static fake clock + "GROUND ROBOT 1" label removed (not real data) */}

      {children}
    </div>
  )
}

/* ─────────────────────────── Map ─────────────────────────── */
function MapViewToggle({ view, onView }: { view: MapView; onView: (v: MapView) => void }) {
  return (
    <div className="inline-flex items-center gap-1 rounded-control border border-line bg-surface-2 p-0.5">
      {(['map', 'sat'] as MapView[]).map((v) => (
        <button
          key={v}
          type="button"
          onClick={() => onView(v)}
          className={`rounded-chip px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors ${
            view === v ? 'bg-accent-weak text-accent' : 'text-text-3 hover:text-text-2'
          }`}
        >
          {v === 'map' ? 'Map' : 'Sat'}
        </button>
      ))}
    </div>
  )
}

function MapPanel({ steer, view, onView, onCollapse }: { steer: number; view: MapView; onView: (v: MapView) => void; onCollapse: () => void }) {
  return (
    <div className="relative h-full min-h-[240px] overflow-hidden rounded-card border border-line bg-surface-inset">
      <LeafletMap view={view} steer={steer} />

      {/* top-left: label + view toggle */}
      <div className="absolute left-4 top-4 z-[500] flex items-center gap-3">
        <span className="label text-text-2">Map</span>
        <MapViewToggle view={view} onView={onView} />
      </div>

      <button type="button" onClick={onCollapse} title="Collapse map (M)" className="absolute right-4 top-4 z-[500] inline-flex h-8 items-center gap-1.5 rounded-control border border-line bg-surface-2 px-2.5 text-[12px] font-medium text-text-2 hover:bg-surface-3 hover:text-text">
        <PipIcon width={14} height={14} />
        Collapse
      </button>
    </div>
  )
}

function MiniMap({ steer, view, onExpand }: { steer: number; view: MapView; onExpand: () => void }) {
  return (
    <div className="group absolute bottom-4 right-4 z-[400] h-[150px] w-[232px] overflow-hidden rounded-control border border-line-strong bg-surface-inset shadow-overlay ring-1 ring-black/40">
      <LeafletMap view={view} steer={steer} interactive={false} showZoom={false} />
      <span className="label pointer-events-none absolute left-2.5 top-2 z-[500] text-text-2">{view === 'sat' ? 'Sat' : 'Map'}</span>
      <button
        type="button"
        onClick={onExpand}
        title="Expand map (M)"
        className="absolute inset-0 z-[500] flex items-start justify-end p-2"
      >
        <span className="grid h-6 w-6 place-items-center rounded-chip bg-surface-2/80 text-text-2 group-hover:text-accent">
          <ExpandIcon width={13} height={13} />
        </span>
      </button>
    </div>
  )
}

/* ─────────────────────────── Joystick ─────────────────────────── */
/* Game-controller analog stick: drag the knob (X = steer, Y = throttle);
   springs back to centre on release. */
function Joystick({ onChange }: { onChange: (x: number, y: number) => void }) {
  const baseRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)
  const rafRef = useRef<number | null>(null)
  const posRef = useRef({ x: 0, y: 0 })
  const [pos, setPos] = useState({ x: 0, y: 0 })
  // CSS sizes the base fluidly (clamp + vh); measure the real width so knob
  // travel and size track whatever the viewport gives us.
  const [dim, setDim] = useState(88)
  useEffect(() => {
    const el = baseRef.current
    if (!el) return
    const measure = () => setDim(el.getBoundingClientRect().width)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const TRAVEL = dim * 0.3 // px the knob can move from centre
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
    set(clamp1(dx), clamp1(-dy)) // up = +throttle
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
    <div className="flex items-center gap-3">
      <div
        ref={baseRef}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        className="relative aspect-square h-[clamp(56px,8.5vh,88px)] shrink-0 touch-none cursor-grab rounded-full border border-line bg-surface-inset ring-1 ring-black/30 active:cursor-grabbing"
        role="slider"
        aria-label="Drive joystick"
        aria-valuetext={`steer ${steerLabel(pos.x)}, throttle ${Math.round(Math.max(0, pos.y) * 100)}%`}
      >
        {/* concentric guide + crosshair */}
        <div className="absolute inset-2 rounded-full border border-line/70" />
        <div className="absolute left-1/2 top-2.5 bottom-2.5 w-px -translate-x-1/2 bg-line" />
        <div className="absolute top-1/2 left-2.5 right-2.5 h-px -translate-y-1/2 bg-line" />
        {/* direction ticks */}
        <span className="absolute left-1/2 top-1 -translate-x-1/2 font-mono text-[10px] tracking-wider text-text-3">FWD</span>
        {/* knob */}
        <div
          className="absolute left-1/2 top-1/2 grid place-items-center rounded-full border border-accent/60 bg-accent-weak shadow-overlay"
          style={{ width: knob, height: knob, transform: `translate(calc(-50% + ${pos.x * TRAVEL}px), calc(-50% + ${-pos.y * TRAVEL}px))` }}
        >
          <span className="h-2.5 w-2.5 rounded-full bg-accent" />
        </div>
      </div>

      <div className="font-mono text-[11px] leading-5 text-text-3">
        <div>
          STEER <span className={Math.abs(pos.x) > 0.02 ? 'text-accent' : 'text-text-2'}>{steerLabel(pos.x)}</span>
        </div>
        <div>
          THR <span className="text-text-2">{Math.round(Math.max(0, pos.y) * 100)}%</span>
        </div>
      </div>
    </div>
  )
}

/* ───────────── On-screen arrow pad (keyboard-mirrored) ───────────── */
/* Shown when no gamepad is connected. Hold a key to act; release returns to
   neutral. Same as the arrow keys: ◄ ► steer, accelerate, stop. */
function HoldKey({
  dir,
  press,
  release,
  tone = 'neutral',
  title,
  children,
}: {
  dir: DriveDir
  press: (d: DriveDir) => void
  release: (d: DriveDir) => void
  tone?: 'neutral' | 'accent'
  title: string
  children: ReactNode
}) {
  const start = (e: React.PointerEvent) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    press(dir)
  }
  const end = () => release(dir)
  const base =
    tone === 'accent'
      ? 'border-accent/40 bg-accent-weak text-accent active:bg-accent active:text-white'
      : 'border-line bg-surface-inset text-text-2 hover:text-text active:bg-surface-3'
  return (
    <button
      type="button"
      title={title}
      onPointerDown={start}
      onPointerUp={end}
      onPointerLeave={end}
      onPointerCancel={end}
      className={`grid h-9 min-w-9 select-none place-items-center gap-1 rounded-control border px-2 font-mono text-[12px] font-semibold transition-colors ${base}`}
    >
      {children}
    </button>
  )
}

function ArrowPad({ press, release }: { press: (d: DriveDir) => void; release: (d: DriveDir) => void }) {
  return (
    <div className="flex items-center gap-1.5" title="Keyboard arrows also work">
      <HoldKey dir="left" press={press} release={release} title="Steer left (←)">◄</HoldKey>
      <HoldKey dir="up" press={press} release={release} tone="accent" title="Accelerate (↑)">
        <BoltIcon width={14} height={14} />
      </HoldKey>
      <HoldKey dir="down" press={press} release={release} title="Stop / brake (↓)">■</HoldKey>
      <HoldKey dir="right" press={press} release={release} title="Steer right (→)">►</HoldKey>
    </div>
  )
}

/* ─────────────────────── Drive control bar ─────────────────────── */
function Segmented<T extends string>({ options, value, onChange, disabled = [], badges }: { options: T[]; value: T; onChange: (v: T) => void; disabled?: T[]; badges?: Partial<Record<T, string>> }) {
  return (
    <div className="inline-flex items-center gap-1 rounded-full bg-surface-inset p-1">
      {options.map((opt) => {
        const active = opt === value
        const isDisabled = disabled.includes(opt)
        return (
          <button key={opt} type="button" disabled={isDisabled} onClick={() => !isDisabled && onChange(opt)} title={isDisabled ? 'Coming soon' : undefined} className={`inline-flex min-w-[40px] items-center justify-center gap-1 rounded-full px-3 py-1.5 font-mono text-[13px] font-semibold transition-colors ${active ? 'bg-accent text-white' : isDisabled ? 'cursor-not-allowed text-text-3/40' : 'text-text-3 hover:text-text-2'}`}>
            {opt}
            {badges?.[opt] && <span className={`text-[11px] ${active ? 'text-white/70' : 'text-text-3'}`}>{badges[opt]}</span>}
          </button>
        )
      })}
    </div>
  )
}

type ToggleState = 'off' | 'pending' | 'confirmed'
function ToggleChip({ label, icon, state, tone = 'success', badge, onClick }: { label: string; icon: ReactNode; state: ToggleState; tone?: 'success' | 'accent'; badge?: ReactNode; onClick: () => void }) {
  let cls = 'border border-line text-text-2 hover:bg-surface-3 hover:text-text'
  if (state === 'pending') cls = 'border border-line bg-surface-3 text-text-3'
  else if (state === 'confirmed') cls = tone === 'success' ? 'border border-success/40 bg-success-weak text-success' : 'border border-accent/40 bg-accent-weak text-accent'
  return (
    <button type="button" onClick={onClick} aria-pressed={state === 'confirmed'} className={`inline-flex h-9 items-center gap-1.5 rounded-control px-2.5 text-[12px] font-semibold transition-colors ${cls}`}>
      <span className={state === 'pending' ? 'argus-blink' : ''}>{icon}</span>
      {label}
      {badge && <span className="ml-0.5">{badge}</span>}
    </button>
  )
}

/** Vertical hairline separating control groups in the drive bar. */
function Divider() {
  return <span className="h-8 w-px shrink-0 self-center bg-line-strong" aria-hidden />
}

function GroupLabel({ children }: { children: string }) {
  return <span className="label mr-2 text-text-3">{children}</span>
}

/** Shows a controller-button glyph above a control when hints are on. */
function WithHint({ show, glyph, children }: { show: boolean; glyph: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      {show && <div className="flex items-center gap-1">{glyph}</div>}
      {children}
    </div>
  )
}

function DriveControlBar({ tele, onStick, padConnected, onOpenController, hints, manual }: { tele: Telemetry; onStick: (x: number, y: number) => void; padConnected: boolean; onOpenController: () => void; hints: boolean; manual: { press: (d: DriveDir) => void; release: (d: DriveDir) => void } }) {
  const setGear = useVehicleStore((s) => s.setGear)
  const setMode = useVehicleStore((s) => s.setMode)
  const toggleIgnition = useVehicleStore((s) => s.toggleIgnition)
  const toggleHeadlights = useVehicleStore((s) => s.toggleHeadlights)
  const setBlinker = useVehicleStore((s) => s.setBlinker)
  const toggleHorn = useVehicleStore((s) => s.toggleHorn)
  const estop = useVehicleStore((s) => s.estop)
  const arm = useVehicleStore((s) => s.arm)

  const driving = tele.safetyState === 'DRIVING'
  const preflight = useVehicleStore((s) => s.preflight)
  const remoteMode = useVehicleStore((s) => s.remote)
  const blinker = tele.lights.blinker
  const st = (on: boolean): ToggleState => (on ? 'confirmed' : 'off')

  return (
    <div className="flex items-center gap-x-4 rounded-card border border-line bg-surface-2 px-5 py-[clamp(8px,1.6vh,14px)]">
      {/* driving controls — grouped zones separated by hairlines */}
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-3">
      <WithHint show={hints} glyph={<><PadGlyph k="lstick" /><PadGlyph k="r2" /></>}>
        <div className="flex flex-col items-center gap-1.5">
          <Joystick onChange={onStick} />
          <button
            type="button"
            onClick={onOpenController}
            className={`inline-flex items-center gap-1.5 rounded-chip px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors hover:brightness-110 ${
              padConnected ? 'bg-success-weak text-success' : 'bg-surface-3 text-text-3 hover:text-text-2'
            }`}
            title="Open controller setup & test"
          >
            <span className={`h-1.5 w-1.5 rounded-full ${padConnected ? 'bg-success' : 'bg-text-3'}`} />
            {padConnected ? 'DualSense' : 'On-screen'}
          </button>
        </div>
      </WithHint>

      {/* arrow keys / on-screen accelerator — only when no gamepad drives */}
      {!padConnected && (
        <>
          <Divider />
          <div className="flex flex-col items-center gap-1.5">
            <ArrowPad press={manual.press} release={manual.release} />
            <span className="font-mono text-[10px] uppercase tracking-wider text-text-3">Keys / hold</span>
          </div>
        </>
      )}

      <Divider />

      <div className="flex items-center">
        <GroupLabel>Ignition</GroupLabel>
        <ToggleChip label={tele.ignition ? 'On' : 'Off'} icon={<IgnitionIcon width={15} height={15} />} state={st(tele.ignition)} tone="accent" onClick={toggleIgnition} />
      </div>

      {remoteMode && tele.ignition && (
        <div className="flex items-center" title={preflight.checks.map((c) => `${c.ok ? 'PASS' : 'FAIL'}  ${c.name}: ${c.detail}`).join('\n') || 'Self-test pending'}>
          <GroupLabel>Self-test</GroupLabel>
          <span
            className={`inline-flex items-center gap-1.5 rounded-chip px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider ${
              !preflight.ran
                ? 'bg-warning-weak text-warning'
                : preflight.pass
                  ? 'bg-success-weak text-success'
                  : 'bg-critical-weak text-critical'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${!preflight.ran ? 'bg-warning argus-blink' : preflight.pass ? 'bg-success' : 'bg-critical argus-blink'}`} />
            {!preflight.ran ? 'Running' : preflight.pass ? `Pass ${preflight.checks.length}/${preflight.checks.length}` : `Fail ${preflight.checks.filter((c) => !c.ok).length}`}
          </span>
        </div>
      )}

      <Divider />

      <WithHint show={hints} glyph={<><PadGlyph k="circle" /><PadGlyph k="cross" /><PadGlyph k="triangle" /></>}>
        <div className="flex items-center">
          <GroupLabel>Gear</GroupLabel>
          <Segmented options={['R', 'N', 'F']} value={tele.gear} onChange={setGear} />
        </div>
      </WithHint>

      <WithHint show={hints} glyph={<><PadGlyph k="r2" /><PadGlyph k="l2" /></>}>
        <div className="flex items-baseline">
          <GroupLabel>Speed</GroupLabel>
          {remoteMode ? (
            <span className="font-mono text-[clamp(20px,2.6vh,26px)] font-bold leading-none tabular-nums text-text">
              {tele.speedKmh.toFixed(1)}<span className="ml-1 text-[12px] font-medium text-text-3">km/h</span>
            </span>
          ) : (
            <span className="font-mono text-[clamp(20px,2.6vh,26px)] font-bold leading-none tabular-nums text-text-3">N/A</span>
          )}
        </div>
      </WithHint>

      <Divider />

      <div className="flex items-center">
        <GroupLabel>Mode</GroupLabel>
        <Segmented options={['MANUAL', 'AUTO']} value={tele.mode} onChange={setMode} disabled={['AUTO']} />
      </div>

      <Divider />

      <div className="flex items-center gap-1.5">
        <WithHint show={hints} glyph={<PadGlyph k="square" />}>
          <ToggleChip label="Lights" icon={<LightsIcon width={15} height={15} />} state={st(tele.lights.headlights)} onClick={toggleHeadlights} />
        </WithHint>
        <WithHint show={hints} glyph={<PadGlyph k="dleft" />}>
          <ToggleChip label="Left" icon={<BlinkerIcon width={15} height={15} className="scale-x-[-1]" />} state={st(blinker === 'left' || blinker === 'hazard')} tone="accent" onClick={() => setBlinker(blinker === 'left' ? 'off' : 'left')} />
        </WithHint>
        <WithHint show={hints} glyph={<PadGlyph k="dright" />}>
          <ToggleChip label="Right" icon={<BlinkerIcon width={15} height={15} />} state={st(blinker === 'right' || blinker === 'hazard')} tone="accent" onClick={() => setBlinker(blinker === 'right' ? 'off' : 'right')} />
        </WithHint>
        <WithHint show={hints} glyph={<PadGlyph k="dup" />}>
          <ToggleChip label="Hazards" icon={<HazardIcon width={15} height={15} />} state={st(blinker === 'hazard')} tone="accent" onClick={() => setBlinker(blinker === 'hazard' ? 'off' : 'hazard')} />
        </WithHint>
        <WithHint show={hints} glyph={<PadGlyph k="r1" />}>
          <ToggleChip label="Horn" icon={<HornIcon width={15} height={15} />} state={st(tele.lights.horn)} onClick={toggleHorn} />
        </WithHint>
      </div>
      </div>

      {/* ARM / E-STOP — pinned right behind a hairline, the one loud element */}
      <Divider />
      <div className="flex shrink-0 items-center gap-2">
        {!driving && (
          <WithHint show={hints} glyph={<PadGlyph k="l1r1" />}>
            <Button variant="primary" onClick={arm} className="h-[clamp(40px,5.2vh,44px)] px-6 text-[15px] font-bold tracking-wide">
              ARM
            </Button>
          </WithHint>
        )}
        <WithHint show={hints} glyph={<PadGlyph k="options" />}>
          <Button variant="danger" onClick={estop} className="h-[clamp(40px,5.2vh,44px)] px-7 text-[15px] font-bold tracking-wide shadow-[0_0_0_3px_rgba(255,77,77,0.18)]">
            E-STOP
          </Button>
        </WithHint>
      </div>
    </div>
  )
}

/* ─────────────────────── View controls (header) ─────────────────── */
function IconToggle({ active, onClick, title, children }: { active?: boolean; onClick: () => void; title: string; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={active} className={`grid h-9 w-9 place-items-center rounded-control border transition-colors ${active ? 'border-accent/40 bg-accent-weak text-accent' : 'border-line bg-surface-2 text-text-2 hover:bg-surface-3 hover:text-text'}`}>
      {children}
    </button>
  )
}

/* ─────────────────────────── Screen ─────────────────────────── */
export function CockpitScreen() {
  useDriveLoop()
  const [driveKey, setDriveKeyState] = useState<string | null>(() => getDriveKey())
  const [entered, setEntered] = useState(false)
  const showConnect = isDriveMode() && !entered
  const remo = useRemoTransport(driveKey, entered)
  const bridge = useBridgeTransport(driveKey, entered)
  const link = bridge.active ? bridge : remo
  const pad = useGamepad()
  // keyboard arrows + on-screen pad drive only when no gamepad and cockpit is shown
  const manual = useManualDrive(!pad.connected && !showConnect)
  const tele = useTelemetry()
  const remoteMode = useVehicleStore((s) => s.remote)
  const setStick = useVehicleStore((s) => s.setStick)
  const toggleRecord = useVehicleStore((s) => s.toggleRecord)

  const [mapCollapsed, setMapCollapsed] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [mapView, setMapView] = useState<MapView>('sat')
  const [controllerOpen, setControllerOpen] = useState(false)
  const [hints, setHints] = useState(false)
  const [assist, setAssist] = useState(false)
  const [voiceOpen, setVoiceOpen] = useState(false)

  // Brain-issued bounded drive. Safety model:
  //  - only asserts while "assist" is on and the assert-loop is running;
  //  - HUMAN OVERRIDE: each tick it re-reads the live command; if it diverged
  //    from what assist last set (a human moved the stick/keys/gamepad), assist
  //    aborts immediately — the human always wins;
  //  - AUTO-NEUTRAL: after the clamped duration it sets neutral once and stops;
  //  - the relay dead-man + the store's DRIVING gate remain the outer guards.
  const assistRef = useRef<AssistState | null>(null)

  const handleDriveIntent = useCallback((intent: DriveIntent) => {
    const store = useVehicleStore.getState()
    if (intent.action === 'stop' || intent.action === 'none') {
      assistRef.current = null
      store.setStick(0, 0)
      return
    }
    const cmd = intentToCommand(intent)
    assistRef.current = {
      steer: cmd.steer,
      throttle: cmd.throttle,
      until: performance.now() + clampDurationMs(intent.durationMs),
    }
    store.setStick(cmd.steer, cmd.throttle)
  }, [])

  const cancelAssist = useCallback(() => {
    if (assistRef.current) {
      assistRef.current = null
      useVehicleStore.getState().setStick(0, 0)
    }
  }, [])

  // Assist assert-loop (20 Hz). Runs only while assist is enabled.
  useEffect(() => {
    if (!assist) {
      cancelAssist()
      return
    }
    const id = setInterval(() => {
      const store = useVehicleStore.getState()
      const step = assistStep(assistRef.current, store.command, performance.now())
      switch (step.kind) {
        case 'assert':
          store.setStick(step.steer, step.throttle)
          break
        case 'neutralize':
          assistRef.current = null
          store.setStick(0, 0)
          break
        case 'yield':
          assistRef.current = null // human took over
          break
        case 'idle':
          break
      }
    }, 50)
    return () => clearInterval(id)
  }, [assist, cancelAssist])

  const steer = tele.steerAngleDeg / STEER_MAX_DEG
  const status =
    tele.safetyState === 'DRIVING'
      ? { label: 'TELEOP LIVE', wrap: 'bg-success-weak text-success', dot: 'bg-success' }
      : tele.safetyState === 'STOPPED'
        ? { label: 'STOPPED', wrap: 'bg-warning-weak text-warning', dot: 'bg-warning' }
        : { label: 'LATCHED', wrap: 'bg-critical-weak text-critical', dot: 'bg-critical' }

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
      const k = e.key.toLowerCase()
      if (k === 'm') setMapCollapsed((v) => !v)
      else if (k === 'f') toggleFullscreen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleFullscreen])

  return (
    <div className="flex h-full flex-col gap-[clamp(8px,1.4vh,12px)] p-[clamp(12px,2vh,20px)]">
      {/* single slim bar: module · live telemetry · view controls · status */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-card border border-line bg-surface-2 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold tracking-[-0.005em] text-text">Ground Platform</span>
          <SourceTag>GR-1</SourceTag>
        </div>
        <span className="h-5 w-px bg-line-strong" />
        {/* Unconnected telemetry shows N/A until wired to the real vehicle.
            Steer is real (it's the commanded steering). */}
        <Metric label="Link" value={remoteMode ? 'LIVE' : 'N/A'} valueClass={remoteMode ? 'text-success' : 'text-text-3'} />
        <Metric label="Battery" value={remoteMode ? `${tele.battery.percent}%` : 'N/A'} valueClass={remoteMode ? 'text-text' : 'text-text-3'} />
        <Metric label="HDG" value={remoteMode ? `${tele.headingDeg}\u00B0` : 'N/A'} valueClass={remoteMode ? 'text-text' : 'text-text-3'} />
        <Metric label="Steer" value={steerLabel(steer)} valueClass={Math.abs(steer) > 0.02 ? 'text-accent' : 'text-text'} />
        <Metric label="Temp" value={remoteMode ? `${tele.tempC}\u00B0C` : 'N/A'} valueClass={remoteMode ? 'text-text' : 'text-text-3'} />
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setVoiceOpen((v) => !v)}
            title={voiceOpen ? 'Close the Argus voice panel' : 'Talk to Argus — voice, vision, pre-flight'}
            aria-pressed={voiceOpen}
            className={`inline-flex h-9 items-center gap-1.5 rounded-control border px-2.5 font-mono text-[12px] font-semibold uppercase tracking-wider transition-colors ${
              voiceOpen
                ? 'border-accent/40 bg-accent-weak text-accent'
                : 'border-line bg-surface-2 text-text-3 hover:bg-surface-3 hover:text-text-2'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${voiceOpen ? 'bg-accent' : 'bg-text-3'}`} />
            Argus
          </button>
          <button
            type="button"
            onClick={() => setAssist((v) => !v)}
            title={assist ? 'Brain assist ON — Argus may execute bounded drive nudges' : 'Brain assist OFF — Argus can talk/see but not drive'}
            aria-pressed={assist}
            className={`inline-flex h-9 items-center gap-1.5 rounded-control border px-2.5 font-mono text-[12px] font-semibold uppercase tracking-wider transition-colors ${
              assist
                ? 'border-accent/40 bg-accent-weak text-accent'
                : 'border-line bg-surface-2 text-text-3 hover:bg-surface-3 hover:text-text-2'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${assist ? 'bg-accent' : 'bg-text-3'}`} />
            Assist
          </button>
          <button
            type="button"
            onClick={() => setControllerOpen(true)}
            title={pad.connected ? `Controller connected — ${pad.id}` : 'Controller — connect & test'}
            className={`grid h-9 w-9 place-items-center rounded-control border transition-colors ${
              pad.connected
                ? 'border-success/40 bg-success-weak text-success'
                : 'border-line bg-surface-2 text-text-2 hover:bg-surface-3 hover:text-text'
            }`}
          >
            <GamepadIcon width={18} height={18} />
          </button>
          <button
            type="button"
            onClick={() => setHints((v) => !v)}
            title={hints ? 'Hide controller button hints' : 'Show controller button hints'}
            className={`grid h-9 w-9 place-items-center rounded-control border font-mono text-[12px] font-bold leading-none transition-colors ${
              hints
                ? 'border-accent/40 bg-accent-weak text-accent'
                : 'border-line bg-surface-2 text-text-3 hover:bg-surface-3 hover:text-text-2'
            }`}
          >
            ○△
          </button>
          <IconToggle active={mapCollapsed} onClick={() => setMapCollapsed((v) => !v)} title={mapCollapsed ? 'Show map (M)' : 'Collapse map (M)'}>
            <MapIcon width={17} height={17} />
          </IconToggle>
          <IconToggle active={isFullscreen} onClick={toggleFullscreen} title="Fullscreen (F)">
            {isFullscreen ? <FullscreenExitIcon width={17} height={17} /> : <FullscreenIcon width={17} height={17} />}
          </IconToggle>
          <span className={`inline-flex h-6 items-center gap-1.5 rounded-chip px-2 font-mono text-[12px] font-medium ${status.wrap}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} />
            {status.label}
          </span>
          {isDriveMode() && (
            <button
              type="button"
              onClick={() => {
                clearDriveKey()
                setDriveKeyState(null)
                setEntered(false)
              }}
              title="Log out"
              className="grid h-9 w-9 place-items-center rounded-control border border-line bg-surface-2 text-text-2 transition-colors hover:border-critical/40 hover:bg-critical-weak hover:text-critical"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <div className={`grid min-h-0 flex-1 gap-3 ${mapCollapsed ? 'grid-cols-1' : 'grid-cols-1 lg:grid-cols-[1.7fr_1fr]'}`}>
        <LiveFeed steer={steer} recording={tele.recording} onToggleRecord={toggleRecord}>
          {mapCollapsed && <MiniMap steer={steer} view={mapView} onExpand={() => setMapCollapsed(false)} />}
        </LiveFeed>
        {!mapCollapsed && <MapPanel steer={steer} view={mapView} onView={setMapView} onCollapse={() => setMapCollapsed(true)} />}
      </div>

      <DriveControlBar tele={tele} onStick={setStick} padConnected={pad.connected} onOpenController={() => setControllerOpen(true)} hints={hints} manual={manual} />

      <ControllerPanel open={controllerOpen} onClose={() => setControllerOpen(false)} />

      {/* Argus voice/brain HUD — opened from the header, closed by default */}
      {voiceOpen && (
        <div className="pointer-events-auto fixed right-4 top-24 z-[900] w-[min(340px,calc(100vw-2rem))]">
          <BrainPanel assistEnabled={assist} onDriveIntent={handleDriveIntent} />
        </div>
      )}

      <RemoLinkBadge link={link} />
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

/* ─── Live-hardware link badge (only shown when ?drive=host:port is set) ─── */
function RemoLinkBadge({ link }: { link: RemoLink }) {
  if (!link.active) return null
  const map = {
    connecting: { dot: 'bg-warning', text: 'text-warning', label: 'LINK · CONNECTING' },
    open: { dot: 'bg-success', text: 'text-success', label: 'LINK · LIVE' },
    closed: { dot: 'bg-critical', text: 'text-critical', label: 'LINK · LOST' },
    error: { dot: 'bg-critical', text: 'text-critical', label: 'LINK · ERROR' },
  }[link.status]
  return (
    <div
      title={`Live hardware: ${link.label}`}
      className="pointer-events-none fixed left-4 top-4 z-[1000] inline-flex items-center gap-1.5 rounded-chip border border-line bg-surface-2/90 px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider shadow-overlay backdrop-blur"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${map.dot} ${link.status !== 'open' ? 'argus-blink' : ''}`} />
      <span className={map.text}>{map.label}</span>
    </div>
  )
}
