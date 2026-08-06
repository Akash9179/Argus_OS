import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'ghost' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  children: ReactNode
}

const base =
  'inline-flex items-center justify-center gap-2 rounded-control px-4 h-9 text-[14px] font-semibold ' +
  'transition-colors duration-150 ease-out select-none focus:outline-none ' +
  'focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-40 disabled:pointer-events-none'

const variants: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent-strong',
  ghost: 'border border-line text-text-2 hover:bg-surface-3 hover:text-text',
  danger: 'bg-critical text-white hover:brightness-110',
}

export function Button({ variant = 'primary', children, className = '', ...props }: ButtonProps) {
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  )
}
