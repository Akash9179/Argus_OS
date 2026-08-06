import type { ReactNode } from 'react'

/** Label + value metric pair — the shared top-bar / telemetry primitive
 * (DESIGN.md §5: mono uppercase label in --text-3, mono tabular value).
 * `leading` slots an element (e.g. signal bars) between label and value. */
export function Metric({
  label,
  value,
  valueClass = 'text-text',
  leading,
}: {
  label: string
  value: string
  valueClass?: string
  leading?: ReactNode
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[11px] uppercase tracking-wider text-text-3">{label}</span>
      {leading}
      <span className={`font-mono text-[12px] font-medium tabular-nums ${valueClass}`}>{value}</span>
    </div>
  )
}
