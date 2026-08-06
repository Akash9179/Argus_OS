/**
 * Operator clock preferences: timezone and 12/24-hour format.
 *
 * Display only. Everything stored or sent stays UTC (the contract's rule);
 * these preferences change how moments are shown to this operator on this
 * machine, and nothing else. Persisted per browser in localStorage.
 */
import { useSyncExternalStore } from 'react'

export interface ClockPrefs {
  /** IANA zone name, 'UTC', or '' for the machine's own zone. */
  timeZone: string
  twelveHour: boolean
}

const KEY = 'argus.clock'
const DEFAULTS: ClockPrefs = { timeZone: '', twelveHour: false }

let prefs: ClockPrefs = load()
const listeners = new Set<() => void>()

function load(): ClockPrefs {
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return DEFAULTS
    const parsed = JSON.parse(raw) as Partial<ClockPrefs>
    return {
      timeZone: typeof parsed.timeZone === 'string' ? parsed.timeZone : '',
      twelveHour: parsed.twelveHour === true,
    }
  } catch {
    return DEFAULTS
  }
}

export function setClockPrefs(next: Partial<ClockPrefs>): void {
  prefs = { ...prefs, ...next }
  try {
    window.localStorage.setItem(KEY, JSON.stringify(prefs))
  } catch {
    /* private mode: prefs live for the session only */
  }
  listeners.forEach((fn) => fn())
}

export function useClockPrefs(): ClockPrefs {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    () => prefs,
  )
}

export function zoneChoices(): string[] {
  try {
    return Intl.supportedValuesOf('timeZone')
  } catch {
    return ['UTC', 'Europe/London', 'Europe/Berlin', 'Asia/Kolkata', 'Asia/Dubai', 'America/New_York', 'America/Los_Angeles']
  }
}

function zoneOf(p: ClockPrefs): string | undefined {
  return p.timeZone === '' ? undefined : p.timeZone
}

/** "17:35" or "5:35 PM", in the chosen zone. */
export function clockTime(epochSeconds: number, p: ClockPrefs, withSeconds = false): string {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    ...(withSeconds ? { second: '2-digit' as const } : {}),
    hour12: p.twelveHour,
    timeZone: zoneOf(p),
  })
    .format(new Date(epochSeconds * 1000))
    .toUpperCase()
}

/** Short zone label for the menu bar: "Z" for UTC, "GMT+5:30" style otherwise. */
export function zoneLabel(epochSeconds: number, p: ClockPrefs): string {
  if (p.timeZone === 'UTC') return 'Z'
  const part = new Intl.DateTimeFormat('en-GB', {
    timeZone: zoneOf(p),
    timeZoneName: 'short',
  })
    .formatToParts(new Date(epochSeconds * 1000))
    .find((x) => x.type === 'timeZoneName')
  return part?.value ?? ''
}

/** "Thursday 6 August", in the chosen zone. */
export function clockDate(epochSeconds: number, p: ClockPrefs): string {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: zoneOf(p),
  }).format(new Date(epochSeconds * 1000))
}
