import { useGamepadMonitor } from '../input/useGamepadMonitor'
import { GamepadIcon, CloseIcon } from '../ui/icons'

const BUTTON_MAP: { action: string; button: string }[] = [
  { action: 'Steer', button: 'Left stick' },
  { action: 'Drive / accelerate', button: 'R2  ·  right trigger' },
  { action: 'Brake', button: 'L2  ·  left trigger' },
  { action: 'Gear — Forward', button: 'Triangle  △' },
  { action: 'Gear — Neutral', button: 'Cross  ✕' },
  { action: 'Gear — Reverse', button: 'Circle  ○' },
  { action: 'Blinker — Left', button: 'D-pad ◄' },
  { action: 'Blinker — Right', button: 'D-pad ►' },
  { action: 'Hazards', button: 'D-pad ▲' },
  { action: 'Lights', button: 'Square  □' },
  { action: 'Horn', button: 'R1' },
  { action: 'Re-arm', button: 'L1 + R1' },
  { action: 'E-STOP', button: 'Options' },
  { action: 'Record', button: 'Create' },
]

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-6 font-mono text-[11px] uppercase text-text-3">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-inset">
        <div className="h-full rounded-full bg-accent transition-[width] duration-75" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="w-9 text-right font-mono text-[11px] tabular-nums text-text-2">{Math.round(value * 100)}%</span>
    </div>
  )
}

/** A mapped-control chip that lights when its source button(s) are pressed. */
function TestChip({ label, on, tone = 'accent' }: { label: string; on: boolean; tone?: 'accent' | 'success' | 'critical' }) {
  const onCls =
    tone === 'critical'
      ? 'border-critical/50 bg-critical-weak text-critical'
      : tone === 'success'
        ? 'border-success/50 bg-success-weak text-success'
        : 'border-accent/50 bg-accent-weak text-accent'
  return (
    <span
      className={`inline-flex h-7 items-center rounded-chip border px-2.5 font-mono text-[11px] font-semibold uppercase tracking-wider transition-colors ${
        on ? onCls : 'border-line bg-surface-2 text-text-3'
      }`}
    >
      {label}
    </span>
  )
}

export function ControllerPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const m = useGamepadMonitor(open)
  if (!open) return null
  const p = (i: number) => !!m.pressed[i]
  const steerDeg = Math.round(m.steer * 30)

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-6">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative z-10 flex max-h-[88vh] w-full max-w-[600px] flex-col overflow-hidden rounded-card border border-line-strong bg-surface-3 shadow-overlay">
        {/* header */}
        <div className="flex shrink-0 items-center justify-between border-b border-line px-5 py-3.5">
          <div className="flex items-center gap-2.5 text-text">
            <GamepadIcon width={18} height={18} />
            <span className="text-[15px] font-semibold">Controller</span>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-control text-text-2 hover:bg-surface-2 hover:text-text">
            <CloseIcon width={16} height={16} />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* status */}
          <div className="flex items-center gap-3 rounded-control border border-line bg-surface-2 px-4 py-3">
            <span className={`h-2.5 w-2.5 rounded-full ${m.connected ? 'bg-success' : 'bg-text-3'}`} />
            <div className="min-w-0">
              <div className={`text-[14px] font-semibold ${m.connected ? 'text-success' : 'text-text-2'}`}>
                {m.connected ? 'Connected' : 'Not connected'}
              </div>
              <div className="truncate font-mono text-[11px] text-text-3">
                {m.connected ? m.id : 'No controller detected'}
              </div>
            </div>
          </div>

          {/* how to connect */}
          {!m.connected && (
            <ol className="space-y-1.5 rounded-control border border-line bg-surface-2 px-4 py-3 text-[13px] text-text-2">
              <li><span className="mr-1.5 font-mono text-text-3">1.</span>Plug the DualSense in via USB, or pair it over Bluetooth (hold Create + PS until the light bar flashes).</li>
              <li><span className="mr-1.5 font-mono text-text-3">2.</span><span className="text-text">Press any button</span> — the browser only shows a gamepad after the first input.</li>
              <li><span className="mr-1.5 font-mono text-text-3">3.</span>This panel turns green and the controls below light up as you press them.</li>
            </ol>
          )}

          {/* button map */}
          <div>
            <div className="label mb-2 text-text-3">Button map</div>
            <div className="overflow-hidden rounded-control border border-line">
              {BUTTON_MAP.map((r, i) => (
                <div
                  key={r.action}
                  className={`flex items-center justify-between px-4 py-2 ${i % 2 ? 'bg-surface-2/40' : ''}`}
                >
                  <span className="text-[13px] text-text-2">{r.action}</span>
                  <span className="font-mono text-[12px] font-semibold tracking-wide text-text">{r.button}</span>
                </div>
              ))}
            </div>
          </div>

          {/* live tester */}
          {m.connected && (
            <>
              <div className="grid grid-cols-[auto_1fr] gap-4">
                {/* left stick */}
                <div className="flex flex-col items-center gap-1.5">
                  <div className="relative h-[92px] w-[92px] rounded-full border border-line bg-surface-inset">
                    <div className="absolute left-1/2 top-2 bottom-2 w-px -translate-x-1/2 bg-line" />
                    <div className="absolute top-1/2 left-2 right-2 h-px -translate-y-1/2 bg-line" />
                    <div
                      className="absolute left-1/2 top-1/2 h-5 w-5 rounded-full border border-accent/60 bg-accent-weak"
                      style={{ transform: `translate(calc(-50% + ${m.lx * 30}px), calc(-50% + ${m.ly * 30}px))` }}
                    >
                      <span className="absolute inset-0 m-auto h-1.5 w-1.5 rounded-full bg-accent" />
                    </div>
                  </div>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-text-3">L-Stick</span>
                </div>

                {/* triggers + mapped values */}
                <div className="flex flex-col justify-center gap-2.5">
                  <Bar label="R2" value={m.r2} />
                  <Bar label="L2" value={m.l2} />
                  <div className="mt-1 flex items-center gap-5 font-mono text-[12px]">
                    <span className="text-text-3">STEER <span className={Math.abs(m.steer) > 0.02 ? 'text-accent' : 'text-text'}>{steerDeg === 0 ? '0°' : `${Math.abs(steerDeg)}° ${steerDeg > 0 ? 'R' : 'L'}`}</span></span>
                    <span className="text-text-3">THROTTLE <span className={m.throttle > 0.02 ? 'text-accent' : 'text-text'}>{Math.round(m.throttle * 100)}%</span></span>
                  </div>
                </div>
              </div>

              {/* mapped buttons */}
              <div>
                <div className="label mb-2 text-text-3">Press to verify</div>
                <div className="flex flex-wrap gap-1.5">
                  <TestChip label="Gear F" on={p(3)} />
                  <TestChip label="Gear N" on={p(0)} />
                  <TestChip label="Gear R" on={p(1)} />
                  <TestChip label="◄ Left" on={p(14)} />
                  <TestChip label="Right ►" on={p(15)} />
                  <TestChip label="Hazard" on={p(12)} />
                  <TestChip label="Lights" on={p(2)} />
                  <TestChip label="Horn" on={p(5) && !p(4)} />
                  <TestChip label="Re-arm (L1+R1)" on={p(4) && p(5)} tone="success" />
                  <TestChip label="E-Stop" on={p(9)} tone="critical" />
                  <TestChip label="Record" on={p(8)} />
                </div>
              </div>

              <p className="text-[12px] text-text-3">
                While connected, the controller drives the vehicle. R2 = throttle, left stick = steer.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
