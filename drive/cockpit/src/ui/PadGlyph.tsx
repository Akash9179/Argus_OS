/* Recognizable DualSense button prompts. Face buttons use their iconic colours
 * (this is a controller-prompt context, not a status signal), triggers/bumpers
 * are labelled pills with R2 highlighted since it's the drive control. */

const FACE: Record<'triangle' | 'circle' | 'cross' | 'square', { glyph: string; color: string }> = {
  triangle: { glyph: '△', color: '#4ED88A' },
  circle: { glyph: '○', color: '#FF6B8A' },
  cross: { glyph: '✕', color: '#5B9DFF' },
  square: { glyph: '□', color: '#C98BFF' },
}

function Face({ k }: { k: keyof typeof FACE }) {
  const f = FACE[k]
  return (
    <span
      className="grid h-[18px] w-[18px] place-items-center rounded-full border bg-surface-inset text-[11px] font-bold leading-none"
      style={{ color: f.color, borderColor: f.color }}
    >
      {f.glyph}
    </span>
  )
}

function Pill({ label, accent }: { label: string; accent?: boolean }) {
  return (
    <span
      className={`inline-flex h-[18px] items-center rounded-chip border px-1.5 font-mono text-[10px] font-bold leading-none ${
        accent ? 'border-accent/50 bg-accent-weak text-accent' : 'border-line bg-surface-inset text-text-2'
      }`}
    >
      {label}
    </span>
  )
}

export type PadKey =
  | 'triangle'
  | 'circle'
  | 'cross'
  | 'square'
  | 'r1'
  | 'r2'
  | 'l2'
  | 'l1r1'
  | 'options'
  | 'create'
  | 'lstick'
  | 'dleft'
  | 'dright'
  | 'dup'

export function PadGlyph({ k }: { k: PadKey }) {
  switch (k) {
    case 'triangle':
    case 'circle':
    case 'cross':
    case 'square':
      return <Face k={k} />
    case 'r2':
      return <Pill label="R2" accent />
    case 'l2':
      return <Pill label="L2" />
    case 'r1':
      return <Pill label="R1" />
    case 'l1r1':
      return <Pill label="L1+R1" />
    case 'options':
      return <Pill label="OPTIONS" />
    case 'create':
      return <Pill label="CREATE" />
    case 'lstick':
      return <Pill label="L-STICK" />
    case 'dleft':
      return <Pill label="D-pad ◄" />
    case 'dright':
      return <Pill label="D-pad ►" />
    case 'dup':
      return <Pill label="D-pad ▲" />
    default:
      return null
  }
}
