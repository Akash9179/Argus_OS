import type { Telemetry } from '../contract'
import type { CheckResult } from './types'

const band = (
  item: string,
  value: number,
  warnAt: number,
  failAt: number,
  dir: 'low-bad' | 'high-bad',
  fmt: (v: number) => string,
): CheckResult => {
  const bad =
    dir === 'low-bad'
      ? { fail: value < failAt, warn: value < warnAt }
      : { fail: value > failAt, warn: value > warnAt }
  const status: CheckResult['status'] = bad.fail ? 'fail' : bad.warn ? 'warn' : 'ok'
  return { item, status, detail: fmt(value) }
}

export function evaluatePreflight(t: Telemetry): CheckResult[] {
  return [
    band('Battery', t.battery.percent, 40, 20, 'low-bad', (v) => `${v}% (${t.battery.runtimeMin} min)`),
    band('Link', t.linkRttMs, 300, 600, 'high-bad', (v) => `${Math.round(v)} ms round-trip`),
    band('Temperature', t.tempC, 60, 75, 'high-bad', (v) => `${Math.round(v)} °C`),
    // Armed state is informational during pre-flight — you arm AFTER the check,
    // so "not armed" is the normal pre-flight state, not a fault.
    { item: 'Armed', status: 'ok', detail: t.armed ? 'armed' : 'not armed (arm when ready)' },
    { item: 'Safety', status: t.safetyState === 'LATCHED' ? 'fail' : 'ok', detail: t.safetyState.toLowerCase() },
    { item: 'Gear', status: 'ok', detail: t.gear },
  ]
}
