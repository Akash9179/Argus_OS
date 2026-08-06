import type { ReactNode } from 'react'
import { TopBar } from './TopBar'
import { LeftNav } from './LeftNav'
import { RightRail } from './RightRail'

export function AppShell({
  children,
  showCopilot = false,
}: {
  children: ReactNode
  /** Ask Argus copilot rail. Hidden for now; flip to true to bring it back. */
  showCopilot?: boolean
}) {
  return (
    <div className="flex h-screen flex-col bg-bg text-text">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <LeftNav />
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
        {showCopilot && <RightRail />}
      </div>
    </div>
  )
}
