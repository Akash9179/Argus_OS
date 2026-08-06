import type { ReactNode } from 'react'

/** A small controller/keyboard prompt badge — like on-screen button hints in a game. */
export function KeyCap({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex h-[15px] min-w-[15px] items-center justify-center rounded-[3px] border border-line bg-surface-inset px-1 font-mono text-[9px] font-semibold leading-none text-text-3"
    >
      {children}
    </span>
  )
}

/** DualSense face-button glyphs (kept neutral to respect the colour system). */
export const PAD = {
  triangle: '△',
  circle: '○',
  cross: '✕',
  square: '□',
} as const
