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
  },
}))

import { track as api } from '../sdk/client'
import { Operate } from './Operate'

const issueTask = api.issueTask as ReturnType<typeof vi.fn>
const cancelTask = api.cancelTask as ReturnType<typeof vi.fn>

function machine(overrides: Partial<Asset> = {}): Asset {
  return {
    asset_id: 'M1',
    display_name: 'Scout 1',
    status: 'ASSET_STATUS_ACTIVE',
    battery_fraction: 0.8,
    position: { latitude_deg: 51.5, longitude_deg: -0.12 },
    last_heartbeat: new Date().toISOString(),
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
})
afterEach(cleanup)

describe('the mode switch', () => {
  it('does nothing at all when the mode clicked is already in force', async () => {
    // The bug: this click ran the stop path and cancelled a running order.
    renderOperate(aWorld({ tasks: [operatorOrder()] }))

    fireEvent.click(modeButton('Manual'))

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(cancelTask).not.toHaveBeenCalled()
  })

  it("leaves an operator's order running across a trip through Automatic", async () => {
    // The bug: entering Manual cancelled any open order, whoever gave it,
    // and announced it as the station's own.
    renderOperate(aWorld({ tasks: [operatorOrder()] }))

    fireEvent.click(modeButton('Automatic'))
    fireEvent.click(modeButton('Manual'))

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(cancelTask).not.toHaveBeenCalled()
  })

  it('takes back only the order the station issued itself', async () => {
    // Automatic issues an investigate order for the fresh contact...
    const { rerender } = renderOperate(aWorld({ tracks: [contact()] }))
    fireEvent.click(modeButton('Automatic'))
    await waitFor(() => expect(issueTask).toHaveBeenCalled())
    expect(issueTask.mock.calls[0][0].channel).toBe('automatic')

    // ...the stream echoes it back as an open task...
    const stationTask: Task = {
      task_id: 'T-STATION',
      asset_id: 'M1',
      task_type: 'navigate',
      phrase: 'drive to a point on the map',
      status: 'TASK_STATE_RUNNING',
      issued_by: { channel: 'automatic' },
      ordered_by: '',
      reason: 'because it was ordered automatically, without anyone being asked',
    }
    rerender(
      <Operate
        world={aWorld({ tracks: [contact()], tasks: [stationTask] })}
        link="good"
        theme="dark"
      />,
    )

    // ...and dropping to Manual withdraws exactly that order.
    fireEvent.click(modeButton('Manual'))
    await waitFor(() => expect(cancelTask).toHaveBeenCalledWith('T-STATION'))
  })

  it("leaves another station's automatic order alone", async () => {
    // The channel says a station issued it. It does not say this station
    // did, and taking back another station's order would be the operator-
    // order bug wearing a different channel.
    const foreign: Task = {
      task_id: 'T-ELSEWHERE',
      asset_id: 'M1',
      task_type: 'navigate',
      phrase: 'drive to a point on the map',
      status: 'TASK_STATE_RUNNING',
      issued_by: { channel: 'automatic' },
      ordered_by: '',
      reason: 'because it was ordered automatically, without anyone being asked',
    }
    renderOperate(aWorld({ tasks: [foreign] }))

    fireEvent.click(modeButton('Automatic'))
    fireEvent.click(modeButton('Manual'))

    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(cancelTask).not.toHaveBeenCalled()
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
