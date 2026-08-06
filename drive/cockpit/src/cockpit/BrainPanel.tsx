import { useCallback, useState } from 'react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { useVoice } from '../brain/useVoice'
import { useCameraFrame } from '../brain/useCameraFrame'
import { postTurn } from '../brain/brainClient'
import { evaluatePreflight } from '../brain/preflight'
import { useTelemetry } from '../state/store'
import type { DriveIntent, CheckResult } from '../brain/types'

interface Turn {
  role: 'user' | 'brain'
  text: string
}

const STATUS_CLASS: Record<CheckResult['status'], string> = {
  ok: 'text-success',
  warn: 'text-warning',
  fail: 'text-critical',
}

export function BrainPanel({
  assistEnabled,
  onDriveIntent,
}: {
  assistEnabled: boolean
  onDriveIntent: (intent: DriveIntent) => void
}) {
  const { supported, listening, startListening, speak } = useVoice()
  const { ready: cameraReady, error: cameraError, start: startCamera, grab: grabFrame, videoEl } =
    useCameraFrame()
  const telemetry = useTelemetry()
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [preflight, setPreflight] = useState<CheckResult[] | null>(null)

  const handleFinal = useCallback(
    async (text: string) => {
      setTurns((t) => [...t, { role: 'user', text }])
      setBusy(true)
      try {
        const frame = cameraReady ? await grabFrame() : undefined
        const pf = evaluatePreflight(telemetry)
        if (/pre-?flight|check/i.test(text)) setPreflight(pf)
        const reply = await postTurn({
          transcript: text,
          cameraFrameJpegBase64: frame,
          telemetry,
          preflight: pf,
          recentTurns: turns.slice(-6),
        })
        setTurns((t) => [...t, { role: 'brain', text: reply.speech }])
        speak(reply.speech)
        if (reply.driveIntent && reply.driveIntent.action !== 'none' && assistEnabled) {
          onDriveIntent(reply.driveIntent)
        }
      } catch (err) {
        const msg = `Brain unavailable: ${err instanceof Error ? err.message : String(err)}`
        setTurns((t) => [...t, { role: 'brain', text: msg }])
      } finally {
        setBusy(false)
      }
    },
    [assistEnabled, cameraReady, grabFrame, onDriveIntent, speak, telemetry, turns],
  )

  const status = listening ? 'Listening…' : busy ? 'Thinking…' : 'Hold to talk'

  return (
    <Card>
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-text-2">
            Argus · Voice
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted">
            {assistEnabled ? 'assist on' : 'assist off'}
          </span>
        </div>

        {!supported && (
          <p className="text-[13px] text-muted">Voice needs Chrome (Web Speech API).</p>
        )}

        {/* Camera preview — P1 stand-in for the vehicle's eye */}
        <div className="overflow-hidden rounded-control border border-line bg-surface-inset">
          <video
            ref={videoEl}
            muted
            playsInline
            className={`h-32 w-full object-cover ${cameraReady ? '' : 'hidden'}`}
          />
          {!cameraReady && (
            <button
              type="button"
              onClick={startCamera}
              className="flex h-32 w-full items-center justify-center font-mono text-[11px] uppercase tracking-wider text-text-3 hover:text-text-2"
            >
              {cameraError ? `Camera: ${cameraError}` : 'Enable camera (Argus’s eye)'}
            </button>
          )}
        </div>

        {preflight && (
          <div className="flex flex-col gap-1 rounded-control border border-line bg-surface-inset p-2.5">
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-text-3">Pre-flight</span>
            {preflight.map((c) => (
              <div key={c.item} className="flex items-baseline justify-between font-mono text-[11px]">
                <span className="text-text-2">{c.item}</span>
                <span className={STATUS_CLASS[c.status]}>
                  {c.status.toUpperCase()} · {c.detail}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto text-[13px]">
          {turns.length === 0 && (
            <p className="text-muted">Hold to talk, then ask what Argus sees or to run a pre-flight.</p>
          )}
          {turns.map((t, i) => (
            <p key={i} className={t.role === 'user' ? 'text-text-2' : 'text-text'}>
              <span className="font-semibold">{t.role === 'user' ? 'You: ' : 'Argus: '}</span>
              {t.text}
            </p>
          ))}
        </div>

        <Button disabled={!supported || busy || listening} onClick={() => startListening(handleFinal)}>
          {status}
        </Button>
      </div>
    </Card>
  )
}
