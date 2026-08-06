import type { ComponentType, SVGProps } from 'react'
import { AssetIcon } from '../ui/icons'

type IconType = ComponentType<SVGProps<SVGSVGElement>>

interface NavItem {
  id: string
  label: string
  Icon: IconType
}

// Trimmed to the only live module for now. More modules (Dashboard, Alerts,
// Tracks, Targeting, Ask Argus) return as they're built.
const items: NavItem[] = [{ id: 'ground', label: 'Ground Platform', Icon: AssetIcon }]

const ACTIVE = 'ground'

function NavButton({ item }: { item: NavItem }) {
  const active = item.id === ACTIVE
  const { Icon } = item
  return (
    <button
      type="button"
      aria-label={item.label}
      className="group relative flex h-12 w-full items-center justify-center"
    >
      {active && <span className="absolute left-0 h-7 w-0.5 rounded-r bg-accent" />}
      <span
        className={`grid h-10 w-10 place-items-center rounded-control transition-colors duration-150 ${
          active
            ? 'bg-accent-weak text-accent'
            : 'text-text-3 hover:bg-surface-3 hover:text-text-2'
        }`}
      >
        <Icon />
      </span>
      <span className="pointer-events-none absolute left-[58px] z-20 hidden whitespace-nowrap rounded-control border border-line bg-surface-3 px-2 py-1 text-[12px] text-text-2 shadow-overlay group-hover:block">
        {item.label}
      </span>
    </button>
  )
}

export function LeftNav() {
  return (
    <nav className="flex w-16 shrink-0 flex-col items-center border-r border-line bg-surface-1 py-3">
      <div className="flex w-full flex-col gap-1">
        {items.map((item) => (
          <NavButton key={item.id} item={item} />
        ))}
      </div>
    </nav>
  )
}
