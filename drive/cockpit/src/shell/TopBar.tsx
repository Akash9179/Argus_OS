export function TopBar() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface-1 pl-5 pr-6">
      <div className="text-[15px] font-bold tracking-[0.06em] text-text">ARGUS</div>
      {/* Placeholder mission-control stats (3 CAM ACTIVE / STATUS NOMINAL /
          Sensors / Pipeline / Detections) removed — they were static fakes.
          Real link/status lives in the cockpit's own bar. */}
    </header>
  )
}
