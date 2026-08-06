import type { ReactNode } from 'react'

type Tint = 'critical' | 'warning' | 'info' | 'success' | 'neutral'

const iconTint: Record<Tint, string> = {
  critical: 'text-critical',
  warning: 'text-warning',
  info: 'text-info',
  success: 'text-success',
  neutral: 'text-text-2',
}

const bracket: Record<Tint, string> = {
  critical: 'border-critical/50',
  warning: 'border-warning/50',
  info: 'border-info/50',
  success: 'border-success/50',
  neutral: 'border-line-strong',
}

interface StatCardProps {
  label: string
  stat: ReactNode
  /** Small icon shown top-right inside a corner-bracket frame. */
  icon?: ReactNode
  tint?: Tint
  sub?: ReactNode
}

/** KPI card: label + big mono stat + corner-bracket framed icon. */
export function StatCard({ label, stat, icon, tint = 'neutral', sub }: StatCardProps) {
  return (
    <div className="relative rounded-card border border-line bg-surface-2 p-5">
      {icon && (
        <div className="absolute right-4 top-4">
          {/* corner-bracket frame — L-tick motif */}
          <div className="relative grid h-9 w-9 place-items-center">
            <span className={`absolute left-0 top-0 h-2.5 w-2.5 border-l border-t ${bracket[tint]}`} />
            <span className={`absolute right-0 top-0 h-2.5 w-2.5 border-r border-t ${bracket[tint]}`} />
            <span className={`absolute bottom-0 left-0 h-2.5 w-2.5 border-b border-l ${bracket[tint]}`} />
            <span className={`absolute bottom-0 right-0 h-2.5 w-2.5 border-b border-r ${bracket[tint]}`} />
            <span className={iconTint[tint]}>{icon}</span>
          </div>
        </div>
      )}
      <div className="label">{label}</div>
      <div className="mt-3 font-mono text-[30px] font-bold leading-none tabular-nums text-text">
        {stat}
      </div>
      {sub && <div className="mt-2 text-[12px] text-text-3">{sub}</div>}
    </div>
  )
}
