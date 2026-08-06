import { useCallback, useRef, useState } from 'react'

// P1 camera stand-in: grabs frames from the operator device camera via
// getUserMedia. This is the documented swap point for the real vehicle
// (ZED X) feed when it exists — the rest of the brain path is unchanged.
export function useCameraFrame() {
  const videoEl = useRef<HTMLVideoElement | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      if (videoEl.current) {
        videoEl.current.srcObject = stream
        await videoEl.current.play()
        setReady(true)
        setError(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setReady(false)
    }
  }, [])

  const grab = useCallback(async (): Promise<string | undefined> => {
    const v = videoEl.current
    if (!v || !ready || v.videoWidth === 0) return undefined
    const canvas = document.createElement('canvas')
    canvas.width = v.videoWidth
    canvas.height = v.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return undefined
    ctx.drawImage(v, 0, 0)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.7)
    return dataUrl.split(',')[1] // strip "data:image/jpeg;base64,"
  }, [ready])

  return { ready, error, start, grab, videoEl }
}
