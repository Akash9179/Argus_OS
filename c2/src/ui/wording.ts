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

  notBuiltYet: 'Not in this build yet.',

  /** The operating system's own furniture: desktop, dock, application names. */
  shell: {
    desktop: 'Desktop',
    /** The product name the wordmark spells, for assistive technology. */
    brand: 'ARGUS',
    /** Under the mark in the top bar: what kind of station this is. */
    station: 'Ground operations',
    /** The name of the top bar's application strip, for assistive technology. */
    launcher: 'Applications',
    /** Only the applications that exist (founder decision, 12 Oct 2026). */
    apps: {
      operate: 'Operate',
      drive: 'Drive',
    },
    tips: {
      operate: 'The site: map, machines, events, voice.',
      drive: 'Take the wheel of one machine.',
      settings: 'Appearance and time.',
    },
    settings: {
      title: 'Settings',
      close: 'Close settings',
      closeHint: 'Close (Esc)',
      nav: { appearance: 'Appearance', time: 'Time' },
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
    /**
     * A contact whose observations carry no time. Saying "a few seconds
     * ago" would claim a recency nothing reported.
     */
    noTimeReported: 'No time reported',
    seenByNoTime: (who: string) => `Seen by ${who}. No time reported.`,
    lastSeenAgo: (ago: string) => `Last seen ${ago}.`,
    noTimeAlone: 'No time reported.',
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

  /** The Operate screen's own furniture, in the approved card layout. */
  operate: {
    fleet: 'Fleet',
    /** A machine's class, in the letters an operator uses. Unknown reads as itself. */
    classes: { ugv: 'UGV', uav: 'UAV', usv: 'USV', uuv: 'UUV' } as Record<string, string>,
    addMachine: 'Add machine',
    all: 'All',
    orders: 'Orders',
    alerts: 'Alerts',
    viewAll: 'View all',
    fewer: 'Fewer',
    noOrders: 'No orders yet.',
    noAlerts: 'Nothing needs you.',
    /** A proposal the assistant has drawn but nobody has approved. */
    awaitingYou: 'Awaiting you',
    proposedNotSent: (machine: string) => `${machine} · proposed by Argus, not sent`,
    /** Order states, in words. Anything unknown reads as itself. */
    taskState: {
      PENDING: 'Waiting',
      ACCEPTED: 'Accepted',
      RUNNING: 'Under way',
      DONE: 'Done',
      FAILED: 'Failed',
      CANCELLED: 'Stopped',
    } as Record<string, string>,
    map: {
      imagery: 'Imagery',
      zones: 'Zones',
      machines: 'Machines',
      marks: 'Marks',
      credit: "Imagery from this station's local cache",
      noImagery: 'Terrain drawn locally. No imagery is cached for this site yet.',
      zoomIn: 'Zoom in',
      zoomOut: 'Zoom out',
    },
    camera: {
      front: 'Front camera',
      noVideo: 'No video yet',
      noCamera: 'No camera',
      noCameraText: (machine: string) => `${machine} has not reported any cameras.`,
      videoLater: 'Video appears here once it is checked.',
    },
    readings: {
      title: 'Readings',
      live: 'Live',
      quiet: 'Not answering',
      speed: 'Speed',
      battery: 'Battery',
      link: 'Link',
      /**
       * The world model carries no link latency, so the link tile says
       * only when the machine was last heard. Never a verdict like "Good"
       * that nothing measured.
       */
      heard: (ago: string) => `Heard ${ago}`,
      positionSource: 'Position source',
      unverified: 'Unverified',
      currentOrder: 'Current order',
      nothingOrdered: 'Nothing ordered',
      standingByIn: (mode: string) => `Standing by in ${mode}.`,
      standingBy: 'Standing by.',
    },
    activity: 'Recent activity',
    systems: 'Vehicle systems',
    /** The name of the fleet rail's two tabs, for assistive technology. */
    detailTabs: 'Systems and activity',
    asking: 'Asking the machine.',
    noneSelected: 'Select a machine to see its readings.',
  },

  assistant: {
    name: 'ARGUS',
    badge: 'Assistant',
    tagline: 'Proposes. Never moves anything without you.',
    collapse: 'Put the assistant away',
    expand: 'Bring the assistant back',
    /**
     * The request carries the operator's words and nothing else, so the
     * prompt names no machine. The machine an order is for is the one the
     * server resolves, shown on the proposal.
     */
    placeholder: 'Ask about the site, or hold the mic',
    send: 'Send',
    approve: 'Approve and send',
    decline: 'No, drop it',
    checking: 'Checking the order.',
    noChecks: 'The world model could not check this order, so it cannot be approved here. Drop it, or order from the map.',
    checksPassed: (n: number) => `${n} ${n === 1 ? 'check' : 'checks'} passed`,
    needYou: (n: number) => `${n} ${n === 1 ? 'needs' : 'need'} you`,
    blocked: (n: number) => `${n} ${n === 1 ? 'check' : 'checks'} failed`,
    showAll: 'Show all',
    you: 'you',
    byVoice: 'by voice',
    typed: 'typed',
    /** Distance and time, plainly. Never more precise than the figure. */
    distance: (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`),
    eta: (sec: number) => {
      const min = Math.round(sec / 60)
      return min < 1 ? 'under a minute' : `about ${min} min`
    },
    stops: (n: number) => `${n} ${n === 1 ? 'stop' : 'stops'}`,
    noEta: 'time unknown',
    /** The machine has not said where it is, so the way there is unmeasured. */
    noDistance: 'distance unknown',
    unreachable: 'Cannot reach the assistant. Orders go through the map.',
    cannotUnderstand: 'The assistant cannot take orders here. Orders go through the map.',
    suggestions: ['What could go wrong?', 'What is everything doing?'],
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
