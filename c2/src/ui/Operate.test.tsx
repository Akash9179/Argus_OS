/**
 * The Operate screen, tested where it acts rather than where it draws.
 *
 * The first two cases pin real bugs that shipped and were found only by a
 * live browser session: a click an operator reads as a no-op cancelled a
 * running order, and entering Manual cancelled operator orders and
 * announced them as the station's own. They live here so a browser is
 * never again the only thing standing between those bugs and an operator.
 *
 * The map and the voice bar are stubbed out: this file is about orders
 * and wording, and Leaflet has no business in a unit test.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Asset, Task, Track, WorldEvent } from '../sdk/types'
import type { World } from '../state/world'

/** The props Operate last gave the assistant, so its wiring can be driven. */
const assistant = vi.hoisted(() => ({
  props: null as null | { collapsed: boolean; onToggle: () => void; onReach?: (reached: boolean) => void },
}))

vi.mock('./MapView', () => ({ MapView: () => null }))
vi.mock('./Assistant', () => ({
  Assistant: (props: typeof assistant.props) => {
    assistant.props = props
    return null
  },
}))
vi.mock('../sdk/client', () => ({
  Refused: class Refused extends Error {},
  track: {
    issueTask: vi.fn(),
    cancelTask: vi.fn(),
    setAutonomy: vi.fn(),
    tiles: vi.fn(async () => ({ layers: [] })),
    systems: vi.fn(async () => ({ asset_id: 'M1', reported_at: null, rows: [], cameras: [], position_source: null, note: '' })),
    previewTask: vi.fn(),
  },
}))

import { track as api } from '../sdk/client'
import { Operate } from './Operate'
import { agoInWords, say } from './wording'

const issueTask = api.issueTask as ReturnType<typeof vi.fn>
const cancelTask = api.cancelTask as ReturnType<typeof vi.fn>
const setAutonomy = api.setAutonomy as ReturnType<typeof vi.fn>

function machine(overrides: Partial<Asset> = {}): Asset {
  return {
    asset_id: 'M1',
    display_name: 'Scout 1',
    status: 'ASSET_STATUS_ACTIVE',
    battery_fraction: 0.8,
    position: { latitude_deg: 51.5, longitude_deg: -0.12 },
    last_heartbeat: new Date().toISOString(),
    autonomy: 'manual',
    ...overrides,
  }
}

function contact(overrides: Partial<Track> = {}): Track {
  return {
    track_id: 'T-CONTACT',
    display_name: 'Possible person',
    confidence: 0.4,
    position: { latitude_deg: 51.501, longitude_deg: -0.121 },
    ...overrides,
  }
}

function aWorld({
  assets = [machine()],
  tracks = [] as Track[],
  tasks = [] as Task[],
  events = [] as WorldEvent[],
} = {}): World {
  return {
    assets: new Map(assets.map((a) => [a.asset_id, a])),
    telemetry: new Map(),
    tracks: new Map(tracks.map((t) => [t.track_id, t])),
    zones: new Map(),
    tasks: new Map(tasks.map((t) => [t.task_id, t])),
    progress: new Map(),
    events,
  }
}

function operatorOrder(): Task {
  return {
    task_id: 'T-OPERATOR',
    asset_id: 'M1',
    task_type: 'navigate',
    phrase: 'drive to a point on the map',
    status: 'TASK_STATE_RUNNING',
    issued_by: { principal_id: 'operator-1', channel: 'map' },
    ordered_by: 'Operator',
    reason: 'because Operator ordered it at 10:00 Z',
  }
}

function renderOperate(world: World) {
  return render(<Operate world={world} link="good" theme="dark" />)
}

const modeButton = (name: string) => screen.getByRole('button', { name })

beforeEach(() => {
  issueTask.mockReset().mockResolvedValue({ task_id: 'T-STATION' })
  cancelTask.mockReset().mockResolvedValue({})
  setAutonomy.mockReset().mockResolvedValue({})
})
afterEach(cleanup)

describe('the mode', () => {
  it('shows what the server holds, not what this browser remembers', () => {
    renderOperate(aWorld({ assets: [machine({ autonomy: 'automatic' })] }))
    // The toggle is a view of server state. A tab that had its own idea
    // would show an operator a setting that is not in force anywhere.
    expect(modeButton('Automatic').className).toContain('on')
    expect(modeButton('Manual').className).not.toContain('on')
  })

  it('asks the server to change the selected machine, and waits', async () => {
    renderOperate(aWorld())
    fireEvent.click(modeButton('Automatic'))
    await waitFor(() => expect(setAutonomy).toHaveBeenCalledWith('M1', 'automatic'))
  })

  it('does nothing at all when the mode clicked is already in force', async () => {
    // The bug this pins: the click ran a stop path and cancelled a
    // running order, on a click an operator reads as a no-op.
    renderOperate(aWorld({ tasks: [operatorOrder()] }))
    fireEvent.click(modeButton('Manual'))

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(setAutonomy).not.toHaveBeenCalled()
    expect(cancelTask).not.toHaveBeenCalled()
  })

  it('never cancels anything itself, whoever gave the order', async () => {
    // The other bug, and now a structural guarantee rather than a
    // careful branch: switching the mode is the platform's act, so this
    // station has nothing to withdraw and no way to withdraw the wrong
    // thing. Both an operator's order and a platform order must survive
    // C2's involvement entirely.
    const platformOrder: Task = {
      task_id: 'T-PLATFORM',
      asset_id: 'M1',
      task_type: 'navigate',
      phrase: 'drive to a point on the map',
      status: 'TASK_STATE_RUNNING',
      issued_by: { channel: 'automatic' },
      ordered_by: '',
      reason: 'because it was ordered automatically, without anyone being asked',
    }
    for (const task of [operatorOrder(), platformOrder]) {
      cleanup()
      cancelTask.mockClear()
      renderOperate(aWorld({ assets: [machine({ autonomy: 'automatic' })], tasks: [task] }))
      fireEvent.click(modeButton('Manual'))
      await new Promise((resolve) => setTimeout(resolve, 20))
      expect(cancelTask).not.toHaveBeenCalled()
    }
  })

  it('never issues an order of its own accord', async () => {
    // The browser engine is gone. A contact on the map with an automatic
    // machine is the platform's business now, and C2 must stay out of it.
    renderOperate(aWorld({ assets: [machine({ autonomy: 'automatic' })], tracks: [contact()] }))
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(issueTask).not.toHaveBeenCalled()
  })
})

describe('what the rows say', () => {
  it('a machine never heard from claims no position and no hearing', () => {
    renderOperate(
      aWorld({
        assets: [
          machine({
            asset_id: 'M2',
            display_name: 'Ghost',
            last_heartbeat: undefined,
            position: undefined,
            battery_fraction: undefined,
          }),
        ],
      }),
    )
    expect(
      screen.getByText(/Never heard from\. It has not said where it is\./),
    ).toBeTruthy()
  })

  it('a quiet machine gets a past-tense battery and the stale caveat', () => {
    renderOperate(
      aWorld({
        assets: [
          machine({
            display_name: 'Sleeper',
            last_heartbeat: new Date(Date.now() - 300_000).toISOString(),
            battery_fraction: 0.49,
          }),
        ],
      }),
    )
    expect(screen.getByText('Battery was 49%')).toBeTruthy()
    expect(
      screen.getByText(/The map shows where it was, not where it is\./),
    ).toBeTruthy()
  })
})

describe('the plan strip', () => {
  it("prints the server's reason verbatim and never composes its own", () => {
    renderOperate(aWorld({ tasks: [operatorOrder()] }))
    expect(
      screen.getByText(/because Operator ordered it at 10:00 Z/),
    ).toBeTruthy()
    // "you" is a claim about who is reading the screen. The server cannot
    // make it and C2 must not invent it.
    expect(screen.queryByText(/because you ordered/)).toBeNull()
  })
})

describe('a mode this build does not recognise', () => {
  // One case, covering every claim the screen makes about a mode. It is
  // here because three separate overclaims survived a fix to how the mode
  // is displayed: the name was shown as sent while every sentence beside
  // it still asserted the manual promise.
  const newer = () =>
    aWorld({ assets: [machine({ autonomy: 'supervised' })], tracks: [contact()] })

  it('shows the mode as sent rather than as one of ours', () => {
    renderOperate(newer())
    expect(screen.getAllByText(/Supervised/).length).toBeGreaterThan(0)
    expect(modeButton('Manual').className).not.toContain('on')
    expect(modeButton('Automatic').className).not.toContain('on')
  })

  it('never promises what manual promises', () => {
    renderOperate(newer())
    expect(screen.queryByText(/will order this machine nothing else/)).toBeNull()
    expect(screen.queryByText(/The machines are waiting for you/)).toBeNull()
  })

  it('does not invite a click it will drop, and says why', () => {
    renderOperate(newer())
    // The machine is answering, so blaming silence would be a lie.
    expect(screen.queryByText(/is not answering/)).toBeNull()
    expect(screen.queryByText(/Click the map to send/)).toBeNull()
  })

  it('does not offer to send a contact anywhere', () => {
    renderOperate(newer())
    fireEvent.click(screen.getByRole('button', { name: /Possible person/ }))
    expect(screen.queryByText(/is not answering/)).toBeNull()
  })
})

describe('when there is no machine to speak for', () => {
  // An empty fleet, or a site whose only contacts came from a fixed
  // sensor. Every claim on this screen is about a selected machine, so
  // with none selected the screen must make no claims at all.
  const empty = () => aWorld({ assets: [], tracks: [contact()] })

  it('names no mode and makes no promise about one', () => {
    renderOperate(empty())
    expect(screen.queryByText(/The machines are waiting for you/)).toBeNull()
    expect(screen.queryByText(/will order this machine nothing else/)).toBeNull()
    // The mode chip describes a machine's setting. There is no machine.
    expect(document.querySelector('.plan-mode')).toBeNull()
  })

  it('never leaves a control with nothing written on it', () => {
    renderOperate(empty())
    fireEvent.click(screen.getByRole('button', { name: /Possible person/ }))
    const send = screen
      .getAllByRole('button')
      .find((b) => b.className.includes('primary'))
    expect(send).toBeTruthy()
    expect(send!.textContent?.trim()).not.toBe('')
  })
})

describe('a server that sends no mode at all', () => {
  // An older platform. C2 may keep letting the operator task the machine,
  // because refusing would strand them against a server that works. It
  // may not name a mode or repeat a promise on evidence it does not have.
  const silent = () => aWorld({ assets: [machine({ autonomy: undefined })] })

  it('claims no mode and no promise, while still allowing an order', () => {
    renderOperate(silent())
    expect(modeButton('Manual').className).not.toContain('on')
    expect(screen.queryByText(/will order this machine nothing else/)).toBeNull()
    expect(screen.queryByText(/The machines are waiting for you/)).toBeNull()
    // Tasking stays available: the map still invites the click.
    expect(screen.getByText(/Click the map to send/)).toBeTruthy()
  })
})

describe('a machine class', () => {
  // Law 5: the letters an operator reads are data in wording.ts. A class
  // this build does not know still reads as itself.
  it('reads in the letters wording.ts gives it', () => {
    const { container } = renderOperate(aWorld({ assets: [machine({ asset_class: 'ugv' })] }))
    const vtype = container.querySelector('.vtype')!
    expect(vtype.textContent).toBe(say.operate.classes.ugv)
  })

  it('reads an unknown class as itself', () => {
    const { container } = renderOperate(aWorld({ assets: [machine({ asset_class: 'tracked_crawler' })] }))
    expect(container.querySelector('.vtype')!.textContent).toBe('Tracked crawler')
  })

  it('reads a class named like an object built-in as itself', () => {
    const { container } = renderOperate(aWorld({ assets: [machine({ asset_class: 'constructor' })] }))
    expect(container.querySelector('.vtype')!.textContent).toBe('Constructor')
  })
})

describe('the link reading', () => {
  // The world model carries no link latency, so the tile says only what it
  // has: when the machine was last heard. "Good" was a verdict nothing
  // measured.
  it('says when the machine was last heard, and never "Good"', () => {
    const { container } = renderOperate(aWorld())
    const link = [...container.querySelectorAll('.stat')].find(
      (s) => s.querySelector('.k')?.textContent === say.operate.readings.link,
    )!
    expect(link.querySelector('.v')!.textContent).toBe(say.operate.readings.heard(agoInWords(0)))
    expect(screen.queryByText('Good')).toBeNull()
  })
})

describe('a contact with no observation time', () => {
  // The bug this pins: no timestamp read as zero seconds, so the screen
  // said "a few seconds ago" with no evidence at all.
  it('says no time was reported, in the row and in the detail', () => {
    const { container } = renderOperate(
      aWorld({ tracks: [contact({ history: [], contributing_asset_ids: ['M1'] })] }),
    )
    const row = screen.getByRole('button', { name: /Possible person/ })
    expect(row.textContent).toContain(say.detail.noTimeReported)
    expect(row.textContent).not.toMatch(/seconds ago/)
    fireEvent.click(row)
    const detail = container.querySelector('.detail')!
    expect(detail.textContent).toContain(say.detail.noTimeReported)
    expect(detail.textContent).not.toMatch(/seconds ago/)
  })

  it('still gives the age when a time was reported', () => {
    const seen = new Date(Date.now() - 120_000).toISOString()
    renderOperate(aWorld({ tracks: [contact({ history: [{ timestamp: seen }] })] }))
    const row = screen.getByRole('button', { name: /Possible person/ })
    expect(row.textContent).toContain('2 minutes ago')
  })
})

describe('the layout', () => {
  // Founder decision, 12 Oct 2026: the map gets the room. Camera and
  // readings are one strip under it; systems and activity are tabs on the
  // fleet rail; the second cameras card is gone.
  const event: WorldEvent = {
    event_id: 'E1',
    ts: Date.now() / 1000,
    text: 'Scout 1 arrived at the gate.',
    severity: 'info',
    source: 'track',
  }

  it('puts the camera and the readings in one strip under the map', () => {
    const { container } = renderOperate(aWorld())
    const centre = container.querySelector('.col-centre')!
    const strip = centre.querySelector(':scope > .strip')!
    expect(strip).toBeTruthy()
    expect(strip.querySelector('.strip-camera')).toBeTruthy()
    expect(strip.querySelector('.strip-readings')).toBeTruthy()
    // The map and the strip, and nothing else, in the centre column.
    expect(centre.children.length).toBe(2)
  })

  it('has no second cameras card', () => {
    const { container } = renderOperate(aWorld())
    expect(container.querySelector('.cameras-card')).toBeNull()
  })

  it('keeps vehicle systems and recent activity as two tabs on the fleet rail', () => {
    const { container } = renderOperate(aWorld({ events: [event] }))
    const rail = container.querySelector('.col-left') as HTMLElement
    const tabs = within(rail).getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual([say.operate.systems, say.operate.activity])
    expect(tabs[0].getAttribute('aria-selected')).toBe('true')
    expect(screen.queryByText(event.text)).toBeNull()
    fireEvent.click(tabs[1])
    expect(tabs[1].getAttribute('aria-selected')).toBe('true')
    expect(within(rail).getByText(event.text)).toBeTruthy()
  })
})

describe('the assistant rail', () => {
  it('collapses when the voice service is unreachable and expands when it answers', () => {
    const { container } = renderOperate(aWorld())
    const operate = container.querySelector('.operate')!
    expect(assistant.props!.collapsed).toBe(false)

    act(() => assistant.props!.onReach!(false))
    expect(assistant.props!.collapsed).toBe(true)
    expect(operate.classList.contains('is-assistant-away')).toBe(true)

    act(() => assistant.props!.onReach!(true))
    expect(assistant.props!.collapsed).toBe(false)
    expect(operate.classList.contains('is-assistant-away')).toBe(false)
  })

  it('can still be opened by hand while the service is unreachable', () => {
    renderOperate(aWorld())
    act(() => assistant.props!.onReach!(false))
    act(() => assistant.props!.onToggle())
    expect(assistant.props!.collapsed).toBe(false)
  })
})
