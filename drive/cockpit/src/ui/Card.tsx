import type { HTMLAttributes, ReactNode } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  /** Remove default padding (for media/feed panels). */
  flush?: boolean
}

export function Card({ children, flush = false, className = '', ...props }: CardProps) {
  return (
    <div
      className={`rounded-card border border-line bg-surface-2 ${flush ? '' : 'p-5'} ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
