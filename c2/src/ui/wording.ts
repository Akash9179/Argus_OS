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

  find: { placeholder: 'Find a place or a machine', filter: 'Filter', all: 'All' },

  /**
   * The menus this application contributes to the operating system's menu
   * bar. Only Operate is built, so the rest are shown and plainly disabled:
   * hiding them would misrepresent what the system is, and a menu that
   * looks live but does nothing is worse than one that says it is not ready.
   */
  menus: ['View', 'Machines', 'Zones', 'Voice'],
  notBuiltYet: 'Not in this build yet.',

  /** The operating system's own furniture: desktop, dock, application names. */
  shell: {
    desktop: 'Desktop',
    apps: {
      operate: 'Operate',
      drive: 'Drive',
      intel: 'Intel',
      review: 'Review',
      fleet: 'Fleet',
    },
    tips: {
      operate: 'The site: map, machines, events, voice.',
      drive: 'Take the wheel of one machine.',
      settings: 'Zones, machines, people, appearance, AI policy.',
    },
    settings: {
      title: 'Settings',
      nav: { zones: 'Zones', machines: 'Machines', people: 'People', appearance: 'Appearance', time: 'Time', ai: 'AI policy' },
      appearance: {
        heading: 'Appearance',
        sub: 'Dark is easier at night and keeps your eyes adjusted. Day is brighter, for working outside in sunlight.',
        dark: 'Dark', darkNote: 'Default. Best at night.',
        day: 'Day', dayNote: 'High brightness, for sunlight.',
      },
      time: {
        heading: 'Time',
        sub: 'How moments are shown on this station. Records and messages between machines always keep universal time underneath.',
        zone: 'Timezone',
        zoneSystem: 'This machine\u2019s timezone',
        zoneUtc: 'Universal time (UTC)',
        format: 'Clock',
        h24: '24-hour', h24Note: '17:35',
        h12: '12-hour', h12Note: '5:35 PM',
      },
    },
    glance: {
      allQuiet: (n: number) =>
        n === 0
          ? 'No machines connected yet.'
          : `Everything is running. ${n === 1 ? 'One machine' : `${n} machines`} connected, nothing needs you.`,
      linkDown: 'The site link is down. Showing the last thing we were told.',
      backHint: 'Esc returns to the desktop.',
    },
  },

  tools: {
    select: 'Select',
    measure: 'Measure',
    mark: 'Mark a place',
  },

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
    /**
     * The mode belongs to the machine and is held and enforced by the
     * platform (plan decision 10, stage one), so these sentences say what
     * the platform will do rather than what this browser tab will do.
     *
     * They still stop where the claim stops. "Will not send it anywhere"
     * is a promise about the platform acting on its own; it is not a
     * promise that nothing can task the machine, because another operator
     * or a voice order still can. Widening it would be the same overclaim
     * the browser-held version made.
     */
    manualMeans:
      'The platform will not send this machine anywhere on its own. It goes where it is told.',
    automaticMeans:
      'The platform may send this machine to look at something new, when it is the nearest machine free to go, and tells you what it did. You can take control at any time.',
    takeControl: 'Take control',
    /**
     * What the mode promises, short enough to sit at the end of the plan
     * strip's sentence.
     *
     * The platform holds and enforces the mode now (plan decision 10,
     * stage one), so this says what the platform will do. It stops there
     * on purpose: a voice order or another operator can still task a
     * machine set to manual, so this is not a promise that nothing will
     * happen to it.
     */
    manualAssurance: 'The platform will order this machine nothing else on its own.',
    automaticAssurance: 'You can take control at any time.',
    switchedToManual:
      'Switched to Manual. Anything the platform had started on its own has been withdrawn.',
    switchedToAutomatic:
      'Switched to Automatic. The platform may now send this machine to look at something new.',
  },

  plan: {
    heading: 'Doing now',
    nothing: 'Nothing ordered. The machines are waiting for you.',
    nothingFor: 'Nothing ordered.',
    stop: 'Stop',
    sending: 'Sending the order',
    // Why a machine is doing what it is doing comes from the server, on the
    // task itself. It is a sentence about the world, so the server's
    // language file owns it, the same as the order's own wording.
  },

  map: {
    clickToSend: 'Click the map to send the selected machine there',
    cannotSend: 'This machine is not answering, so it cannot be given anywhere to go.',
    // Not a refusal, a redirection: in Automatic the platform decides where
    // this machine goes, and taking control is one click away.
    cannotSendAutomatic: 'The platform is deciding where this machine goes. Switch to Manual to send it yourself.',
    // A mode from a newer platform. We do not know what it permits, so we
    // do not offer to task the machine and we do not pretend to know why.
    cannotSendUnknownMode: (mode: string) =>
      `This machine is set to ${mode}, which this screen does not understand. It cannot be sent from here.`,
    // The one case that still shows a control. A disabled button with no
    // words on it tells an operator nothing about why it will not work.
    noMachineSelected: 'No machine is selected to send.',
    scale: '200 m',
    lastHeard: 'Last heard',
    someTimeAgo: 'a while ago',
    /**
     * A machine we have never heard from. Saying "last heard a while ago"
     * would claim a hearing that never happened.
     */
    notHeard: 'Never heard from',
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
    /**
     * The contact rail's line. The server supplies the place and we supply
     * the observer and the age, so each part is dropped rather than faked
     * when it is not known.
     */
    seenByAgo: (who: string, ago: string) => `Seen by ${who}, ${ago}.`,
  },

  counts: {
    answering: (answering: number, total: number) => `${answering} of ${total} answering`,
  },

  theme: { dark: 'Dark', day: 'Day' },
  signOut: 'Sign out',

  /** Month names, for a time that needs its date. Kept with the other words. */
  months: [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ],

  machine: {
    notAnswering: 'No answer',
    battery: 'Battery',
    /** Shown when a machine has gone quiet, so the map is never read as live. */
    stale: 'The map shows where it was, not where it is.',
    /**
     * A machine that has never reported. Registration carries no position,
     * and a position is only ever written from a heartbeat or a motion
     * sample, so such a machine has none and draws no marker. There is
     * therefore nothing on the map to caveat, and saying where it is shown
     * would describe a pin that is not there.
     */
    neverReported: 'It has not said where it is.',
    /**
     * A battery reading from a machine we cannot hear is a reading from the
     * past. Said in the past tense so it is never mistaken for the charge
     * the machine has now.
     */
    batteryWas: (percent: number) => `Battery was ${percent}%`,
    /** Where a machine was pointing, in the eight points of the compass. */
    heading: (deg: number) =>
      ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(((deg % 360) + 360) % 360 / 45) % 8],
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
    modeFailed: 'That setting was not accepted.',
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
 * A time of day, in UTC, because a site and the people watching it are not
 * always in the same place. Always marked Z: two times in one window, one
 * marked and one not, is an invitation to read the unmarked one as local.
 *
 * One function, used by the menu bar clock and by every marker chip and
 * sentence, so the marking cannot drift between them.
 */
export function clockAt(epochSeconds: number, withSeconds = false): string {
  const iso = new Date(epochSeconds * 1000).toISOString()
  const clock = `${iso.slice(11, withSeconds ? 19 : 16)} Z`
  // Anything not from today carries its date. A bare clock time reads as
  // today, and the machines this matters for are the ones that went quiet
  // last night and are still on the screen this afternoon.
  const today = new Date().toISOString().slice(0, 10)
  if (iso.slice(0, 10) === today) return clock
  const day = new Date(epochSeconds * 1000)
  // Zero padded to match the server's dated form, because a reason phrase
  // from the server and a marker chip from here can sit in one window and
  // must not look like two different conventions.
  const date = String(day.getUTCDate()).padStart(2, '0')
  return `${clock} on ${date} ${say.months[day.getUTCMonth()]}`
}

/**
 * A machine's mode, in words. The two this build knows have their own
 * names; anything else is server vocabulary from a newer platform and is
 * shown as itself, for the same reason an unfamiliar machine status is.
 */
export function modeInWords(mode: string): string {
  if (mode === 'manual') return say.mode.manual
  if (mode === 'automatic') return say.mode.automatic
  return plain(mode)
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
