/**
 * The words this application owns.
 *
 * Sentences about the world (what happened, what a machine is doing, why an
 * order was refused) come from the server's language file and are shown as
 * sent. This file holds only the words for C2's own furniture: buttons,
 * column headings, and the states of the interface itself.
 *
 * Rules, the same as the server's: plain words only, no identifiers, no
 * jargon. If a phrase would confuse someone in their first week, rewrite it.
 */

export const say = {
  app: 'Operate',

  /** Says only that the picture is moving. The site link is stated once, in the menu bar. */
  live: 'Live',

  find: { placeholder: 'Find a place or a machine' },

  signIn: {
    title: 'Sign in',
    prompt: 'Enter your access key to reach the site.',
    field: 'Access key',
    action: 'Sign in',
    refused: 'That key was not accepted. Check it and try again.',
    unreachable: 'Cannot reach the site right now. Check the link and try again.',
  },

  link: {
    connecting: 'Reaching the site',
    good: 'Site link good',
    lost: 'Site link lost',
    lostDetail:
      'Not hearing from the site. What you see is the last thing we were told, not what is happening now.',
  },

  rails: {
    machines: 'Our machines',
    contacts: 'Seen nearby',
    happened: 'What happened',
    noMachines: 'No machines have connected yet.',
    noContacts: 'Nothing seen nearby.',
    noEvents: 'Nothing has happened yet.',
  },

  mode: {
    manual: 'Manual',
    automatic: 'Automatic',
    manualMeans:
      'The machines only do what you tell them. Nothing else without your say-so.',
    automaticMeans:
      'The machines work to their standing orders and tell you what they did. You can take control at any time.',
    takeControl: 'Take control',
    switchedToManual: 'Switched to Manual. The machines will ask before anything else.',
    switchedToAutomatic:
      'Switched to Automatic. The machines will go and look at anything new by themselves.',
  },

  plan: {
    heading: 'Doing now',
    nothing: 'Nothing ordered. The machines are waiting for you.',
    nothingFor: 'Nothing ordered.',
    stop: 'Stop',
    sending: 'Sending the order',
  },

  map: {
    clickToSend: 'Click the map to send the selected machine there',
    cannotSend: 'This machine is not answering, so it cannot be given anywhere to go.',
    scale: '200 m',
    lastHeard: 'Last heard',
    someTimeAgo: 'a while ago',
    patrolRoute: 'Patrol route',
  },

  detail: {
    mightBeWrong: 'This might be wrong.',
    sureOutOfTen: (n: number) => `The machine is ${n} in 10 sure.`,
    where: 'Where',
    moving: 'Moving',
    seenBy: 'Seen by',
    lastSeen: 'Last seen',
    send: 'Send the machine to look',
    keepWatching: 'Keep watching',
    close: 'Close',
    noCamera: 'No camera picture from this machine.',
    notRecorded: 'Not recorded',
    sendNamed: (machine: string) => `Send ${machine} to look`,
    contact: 'Possible contact',
    noFigure: 'The machine has not said how sure it is.',
  },

  counts: {
    answering: (answering: number, total: number) => `${answering} of ${total} answering`,
  },

  theme: { dark: 'Dark', day: 'Day' },
  signOut: 'Sign out',

  machine: {
    notAnswering: 'No answer',
    battery: 'Battery',
    /** Shown when a machine has gone quiet, so the map is never read as live. */
    stale: 'The map shows where it was, not where it is.',
  },

  voice: {
    hold: 'Hold space to talk',
    listening: 'Listening.',
    thinking: 'One moment.',
    youSaid: 'You said: ',
    // Shown when the voice service answers but this deployment cannot
    // hear or cannot think. The map still works, and saying so is more
    // use than an error code.
    unavailable: 'Voice is not available here. Orders go through the map.',
    unreachable: 'Cannot reach the voice service. Orders go through the map.',
    noMicrophone: 'No microphone. Orders go through the map.',
    // The readback. An order never happens on speech alone.
    confirmLabel: 'Confirm this order',
    yes: 'Yes, send it',
    no: 'No',
  },

  errors: {
    orderFailed: 'The order was not accepted.',
  },
}

/**
 * Confidence in tenths, never rounded up and never allowed to reach ten.
 * The world model caps confidence at 0.99 precisely so the system never
 * claims certainty; rounding here would undo that on the last step.
 * Returns null when there is no figure, so the interface can say nothing
 * rather than say zero.
 */
export function outOfTen(confidence: number | undefined): number | null {
  if (confidence === undefined || Number.isNaN(confidence)) return null
  return Math.max(0, Math.min(9, Math.floor(confidence * 10)))
}

/**
 * How long ago, in plain words. Seconds are rounded to five so the number
 * does not flicker, which reads as precision the system does not have.
 */
export function agoInWords(seconds: number): string {
  const n = Math.max(0, Math.round(seconds))
  if (n < 10) return 'a few seconds ago'
  if (n < 60) return `${Math.round(n / 5) * 5} seconds ago`
  const minutes = Math.round(n / 60)
  if (minutes < 60) return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`
  const hours = Math.round(minutes / 60)
  return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`
}

/**
 * The four status colours, and nothing else. Meaning never changes between
 * the themes, only the value.
 */
export type Status = 'ok' | 'warn' | 'act' | 'off'

/**
 * A machine's status word is server vocabulary, so an unknown value must
 * still reach the operator. Anything this build does not recognise reads as
 * itself, in plain words, rather than being forced into a known bucket.
 */
export function assetStatus(status: string | undefined, answering: boolean): Status {
  if (!answering) return 'off'
  switch (status) {
    case 'ASSET_STATUS_OFFLINE':
      return 'off'
    case 'ASSET_STATUS_DEGRADED':
      return 'warn'
    case 'ASSET_STATUS_FAULT':
      return 'act'
    case 'ASSET_STATUS_ACTIVE':
    case 'ASSET_STATUS_STANDBY':
    case 'ASSET_STATUS_UNSPECIFIED':
    case undefined:
      return 'ok'
    default:
      // A status word from a newer machine. It reaches the operator, and it
      // reaches them as something to look at rather than as healthy.
      return 'warn'
  }
}

export function statusInWords(status: string | undefined, answering: boolean): string {
  if (!answering) return say.machine.notAnswering
  if (!status) return 'Connected'
  if (!status.startsWith('ASSET_STATUS_')) {
    // A value from a newer machine. Show it rather than drop it.
    return plain(status)
  }
  const rest = status.slice('ASSET_STATUS_'.length)
  const known: Record<string, string> = {
    STANDBY: 'Standing by',
    ACTIVE: 'Active',
    OFFLINE: 'Offline',
    DEGRADED: 'Not fully healthy',
    FAULT: 'Faulty',
    UNSPECIFIED: 'Connected',
  }
  return known[rest] ?? plain(rest)
}

/**
 * The server's severity vocabulary is info, attention, act, offline.
 * Anything this build does not recognise gets attention, never healthy: a
 * severity added later is far more likely to mean trouble than calm, and
 * showing an unknown state as green is the one mistake that cannot be
 * walked back.
 */
export function severityStatus(severity: string): Status {
  switch (severity) {
    case 'info':
      return 'ok'
    case 'attention':
      return 'warn'
    case 'act':
      return 'act'
    case 'offline':
      return 'off'
    default:
      return 'warn'
  }
}

/** Underscores to spaces, so unknown vocabulary is readable rather than lost. */
export function plain(value: string): string {
  const words = value.replace(/_/g, ' ').trim().toLowerCase()
  return words.charAt(0).toUpperCase() + words.slice(1)
}
