import { useCallback, useRef, useState } from 'react'

// The Web Speech `SpeechRecognition` constructor is non-standard and not in the
// TS DOM lib, so we declare the minimal surface we use. `SpeechRecognitionEvent`
// IS in the DOM lib, so we reuse it for the result callback.
interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  maxAlternatives: number
  onresult: ((e: SpeechRecognitionEvent) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start(): void
  stop(): void
}
type SRCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): SRCtor | null {
  const w = window as unknown as { SpeechRecognition?: SRCtor; webkitSpeechRecognition?: SRCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function useVoice() {
  const Ctor = getRecognitionCtor()
  const supported = Ctor !== null && 'speechSynthesis' in window
  const [listening, setListening] = useState(false)
  const recRef = useRef<SpeechRecognitionLike | null>(null)

  const startListening = useCallback(
    (onFinal: (text: string) => void) => {
      if (!Ctor) return
      const rec = new Ctor()
      rec.lang = 'en-US'
      rec.interimResults = false
      rec.maxAlternatives = 1
      rec.onresult = (e: SpeechRecognitionEvent) => {
        const text = e.results[e.results.length - 1][0].transcript.trim()
        if (text) onFinal(text)
      }
      rec.onend = () => setListening(false)
      rec.onerror = () => setListening(false)
      recRef.current = rec
      setListening(true)
      rec.start()
    },
    [Ctor],
  )

  const stopListening = useCallback(() => {
    recRef.current?.stop()
    setListening(false)
  }, [])

  const speak = useCallback((text: string) => {
    if (!('speechSynthesis' in window)) return
    const u = new SpeechSynthesisUtterance(text)
    u.rate = 1.0
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(u)
  }, [])

  return { supported, listening, startListening, stopListening, speak }
}
