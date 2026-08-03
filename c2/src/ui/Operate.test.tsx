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
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Asset, Task, Track } from '../sdk/types'
import type { World } from '../state/world'

vi.mock('./MapView', () => ({ MapView: () => null }))
vi.mock('./VoiceBar', () => ({ VoiceBar: () => null }))
vi.mock('../sdk/client', () => ({
  Refused: class Refused extends Error {},
  track: {
    issueTask: vi.fn(),
    cancelTask: vi.fn(),
    setAutonomy: vi.fn(),
  },
}))

import { track as api } from '../sdk/client'
import { Operate } from './Operate'

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
} = {}): World {
  return {
    assets: new Map(assets.map((a) => [a.asset_id, a])),
    telemetry: new Map(),
    tracks: new Map(tracks.map((t) => [t.track_id, t])),
    zones: new Map(),
    tasks: new Map(tasks.map((t) => [t.task_id, t])),
    progress: new Map(),
    events: [],
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
