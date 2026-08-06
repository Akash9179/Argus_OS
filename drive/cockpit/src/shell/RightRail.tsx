import { Button } from '../ui/Button'
import { MicIcon, SendIcon } from '../ui/icons'

function OperatorMessage({ children }: { children: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-card rounded-tr-sm bg-accent-weak px-3.5 py-2.5 text-[14px] leading-relaxed text-text">
        {children}
      </div>
    </div>
  )
}

function ArgusReply({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[88%] rounded-card rounded-tl-sm border border-line bg-surface-2 px-3.5 py-2.5 text-[14px] leading-relaxed text-text-2">
        {children}
      </div>
    </div>
  )
}

function AlertReply({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-start">
      <div className="relative max-w-[88%] overflow-hidden rounded-card rounded-tl-sm bg-critical-weak px-3.5 py-2.5 pl-4 text-[14px] leading-relaxed text-text">
        <span className="absolute inset-y-0 left-0 w-0.5 bg-critical" />
        {children}
      </div>
    </div>
  )
}

export function RightRail() {
  return (
    <aside className="flex w-[360px] shrink-0 flex-col border-l border-line bg-surface-1">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-line px-5">
        <span className="label text-text-2">Ask Argus</span>
        <span className="font-mono text-[11px] uppercase tracking-wider text-text-3">Copilot</span>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto bg-surface-inset px-4 py-5">
        <OperatorMessage>Send GR-1 on a patrol of the north gate.</OperatorMessage>

        <ArgusReply>
          Routing <span className="font-semibold text-text">GR-1</span> to the north gate now —
          ETA <span className="font-semibold text-text">2:40</span>. I'll watch the feed and flag
          anything above <span className="font-semibold text-text">L2</span>.
        </ArgusReply>

        <AlertReply>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[12px] font-semibold uppercase tracking-wider text-critical">
              ● L3 Alert
            </span>
          </div>
          <p className="mt-1.5">
            Person detected at <span className="font-mono font-semibold">3.2m</span> on the dirt
            track ahead of GR-1. Track{' '}
            <span className="font-mono font-semibold text-text">TRK-0847</span> opened.
          </p>
        </AlertReply>

        <OperatorMessage>Hold position and keep eyes on them.</OperatorMessage>

        <ArgusReply>
          Holding <span className="font-semibold text-text">GR-1</span>. Subject is stationary,
          range steady at <span className="font-mono font-semibold text-text">3.2m</span>. Link
          latency nominal at <span className="font-mono font-semibold text-text">187ms</span>.
        </ArgusReply>
      </div>

      <div className="shrink-0 border-t border-line p-3">
        <div className="flex items-center gap-2 rounded-control border border-line bg-surface-2 px-3 py-2">
          <input
            type="text"
            placeholder="Ask Argus anything…"
            className="min-w-0 flex-1 bg-transparent text-[14px] text-text placeholder:text-text-3 focus:outline-none"
          />
          <button
            type="button"
            aria-label="Voice input"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-control text-text-3 hover:bg-surface-3 hover:text-text-2"
          >
            <MicIcon width={18} height={18} />
          </button>
          <Button variant="primary" className="h-8 px-3" aria-label="Send">
            <SendIcon width={16} height={16} />
            Send
          </Button>
        </div>
      </div>
    </aside>
  )
}
