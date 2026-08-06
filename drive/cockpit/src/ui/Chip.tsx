import type { ReactNode } from 'react'

type Severity = 'critical' | 'warning' | 'info' | 'success' | 'neutral'

const dotColor: Record<Severity, string> = {
  critical: 'bg-critical',
  warning: 'bg-warning',
  info: 'bg-info',
  success: 'bg-success',
  neutral: 'bg-text-3',
}

const washBg: Record<Severity, string> = {
  critical: 'bg-critical-weak',
  warning: 'bg-warning-weak',
  info: 'bg-info-weak',
  success: 'bg-success-weak',
  neutral: 'bg-surface-3',
}

const textColor: Record<Severity, string> = {
  critical: 'text-critical',
  warning: 'text-warning',
  info: 'text-info',
  success: 'text-success',
  neutral: 'text-text-2',
}

interface ChipProps {
  severity?: Severity
  children: ReactNode
  /** Hide the leading status dot. */
  dot?: boolean
  className?: string
}

/** Severity pill: leading dot + label. */
export function Chip({ severity = 'neutral', children, dot = true, className = '' }: ChipProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-chip px-2 h-6 text-[12px] font-semibold ${washBg[severity]} ${textColor[severity]} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dotColor[severity]}`} />}
      {children}
    </span>
  )
}

interface SourceTagProps {
  children: ReactNode
  className?: string
}

/** Mono source tag, e.g. CAM-01 — accent-weak wash. */
export function SourceTag({ children, className = '' }: SourceTagProps) {
  return (
    <span
      className={`inline-flex items-center rounded-chip bg-accent-weak px-2 h-6 font-mono text-[12px] font-medium tracking-wide text-accent ${className}`}
    >
      {children}
    </span>
  )
}
