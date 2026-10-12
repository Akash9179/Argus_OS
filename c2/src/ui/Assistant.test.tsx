/**
 * The assistant, tested where it acts.
 *
 * An order typed here must never be issued by this panel. It goes to the
 * voice service, comes back as a readback, is previewed by the world model,
 * and is only ever sent by answering the readback yes. These cases pin
 * that chain and the two ways it must refuse to shortcut it: a failed
 * check disables the yes, and a no is a no.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { TaskPreview } from '../sdk/types'
import type { Exchange } from '../sdk/voice'

vi.mock('../sdk/session', () => ({ savedToken: () => 'tok' }))
vi.mock('../sdk/client', () => ({
  Refused: class Refused extends Error {},
  track: { previewTask: vi.fn() },
}))
vi.mock('../sdk/voice', () => ({
  capabilities: vi.fn(),
  say: vi.fn(),
  listen: vi.fn(),
  confirm: vi.fn(),
  play: vi.fn(),
  PushToTalk: class {
    start = vi.fn()
    stop = vi.fn(async () => null)
    recording = false
  },
}))

import { track as api } from '../sdk/client'
import * as voice from '../sdk/voice'
import { Assistant, VOICE_RETRY_MS } from './Assistant'
import { say } from './wording'

const previewTask = api.previewTask as ReturnType<typeof vi.fn>
const capabilities = voice.capabilities as ReturnType<typeof vi.fn>
const sayText = voice.say as ReturnType<typeof vi.fn>
const confirm = voice.confirm as ReturnType<typeof vi.fn>

function orderExchange(): Exchange {
  return {
    exchange_id: 'X1',
    heard: 'patrol the north fence with Tessy',
    spoken: 'Patrol the north fence with Tessy. Shall I send it?',
    kind: 'order',
    needs_confirmation: true,
    action: {
      machine: 'Tessy',
      task_type: 'patrol',
      place: 'North fence',
      asset_id: 'M1',
      waypoints: [{ latitude_deg: 51.5, longitude_deg: -0.12 }],
    },
    audio: null,
    audio_format: 'wav',
  }
}

function preview(overrides: Partial<TaskPreview> = {}): TaskPreview {
  return {
    asset_id: 'M1',
    task_type: 'patrol',
    waypoints: [{ latitude_deg: 51.5, longitude_deg: -0.12 }],
    path: [
      { latitude_deg: 51.49, longitude_deg: -0.12 },
      { latitude_deg: 51.5, longitude_deg: -0.12 },
    ],
    distance_m: 800,
    eta_sec: 540,
    speed_mps_assumed: 1.5,
    checks: [
      { id: 'answering', state: 'pass', text: 'Tessy is answering.', source: 'From its last heartbeat.' },
      { id: 'keep_out', state: 'needs_you', text: 'This route crosses Keep out.', source: 'From the site zone list.' },
    ],
    can_send: true,
    ...overrides,
  }
}

const onProposal = vi.fn()

function renderPanel({ collapsed = false, onReach = undefined as undefined | ((reached: boolean) => void) } = {}) {
  return render(
    <Assistant collapsed={collapsed} onToggle={() => undefined} onProposal={onProposal} onReach={onReach} />,
  )
}

async function typeAnOrder() {
  renderPanel()
  await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveProperty('disabled', true))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'patrol the north fence with Tessy' } })
  fireEvent.submit(screen.getByRole('textbox').closest('form')!)
  await waitFor(() => expect(screen.getByRole('button', { name: say.assistant.approve })).toBeTruthy())
}

beforeEach(() => {
  capabilities.mockResolvedValue({ can_hear: false, can_speak: false, can_understand: true, character: 'argus' })
  sayText.mockResolvedValue(orderExchange())
  previewTask.mockResolvedValue(preview())
  confirm.mockResolvedValue({ ...orderExchange(), spoken: 'Sent.', needs_confirmation: false, action: null })
  onProposal.mockReset()
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('an order typed to the assistant', () => {
  it('is previewed by the world model and drawn, and nothing is sent', async () => {
    await typeAnOrder()
    expect(previewTask).toHaveBeenCalledWith({
      asset_id: 'M1',
      task_type: 'patrol',
      waypoints: [{ latitude_deg: 51.5, longitude_deg: -0.12 }],
      channel: 'voice',
    })
    expect(onProposal).toHaveBeenCalledWith(preview().path)
    expect(confirm).not.toHaveBeenCalled()
    // The checks are the server's words, shown with their sources.
    expect(screen.getByText('This route crosses Keep out.')).toBeTruthy()
    expect(screen.getByText('From the site zone list.')).toBeTruthy()
    expect(screen.getByText(say.assistant.needYou(1))).toBeTruthy()
    // The machine named is the one the server resolved, on the card.
    expect(screen.getByText(/^Tessy · /)).toBeTruthy()
  })

  it('is sent only when the readback is answered yes', async () => {
    await typeAnOrder()
    fireEvent.click(screen.getByRole('button', { name: say.assistant.approve }))
    await waitFor(() => expect(confirm).toHaveBeenCalledWith('tok', 'X1', true))
    expect(onProposal).toHaveBeenLastCalledWith(null)
  })

  it('is dropped when the readback is answered no', async () => {
    await typeAnOrder()
    fireEvent.click(screen.getByRole('button', { name: say.assistant.decline }))
    await waitFor(() => expect(confirm).toHaveBeenCalledWith('tok', 'X1', false))
  })

  it('cannot be approved while a check has failed', async () => {
    previewTask.mockResolvedValue(
      preview({
        can_send: false,
        checks: [{ id: 'answering', state: 'fail', text: 'Tessy is not answering.', source: 'From its last heartbeat.' }],
      }),
    )
    await typeAnOrder()
    expect((screen.getByRole('button', { name: say.assistant.approve }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(say.assistant.blocked(1))).toBeTruthy()
  })

  it('shows why, when the world model refuses it at the moment of sending', async () => {
    // The checks passed when proposed. By the yes, the machine had gone
    // quiet, and the world model refused. The person reads its reason.
    confirm.mockResolvedValue({
      ...orderExchange(),
      kind: 'unclear',
      needs_confirmation: false,
      action: null,
      spoken: 'That order was not accepted. Tessy has not answered since 14:02 Z.',
    })
    await typeAnOrder()
    fireEvent.click(screen.getByRole('button', { name: say.assistant.approve }))
    await waitFor(() =>
      expect(screen.getByText('That order was not accepted. Tessy has not answered since 14:02 Z.')).toBeTruthy(),
    )
    expect(screen.queryByRole('button', { name: say.assistant.approve })).toBeNull()
  })

  it('never reads an unknown distance as zero', async () => {
    // The machine has not said where it is, so the way there is unknown.
    previewTask.mockResolvedValue(preview({ distance_m: null, eta_sec: null, speed_mps_assumed: null }))
    await typeAnOrder()
    expect(screen.queryByText(/(^|\s)0 m(\s|$)/)).toBeNull()
    expect(screen.getByText(new RegExp(`${say.assistant.noDistance} · ${say.assistant.noEta}`))).toBeTruthy()
  })

  it('cannot be approved when the checks could not be run', async () => {
    // An order the world model could not look at is not offered as one it
    // did. The readback stays so it can be dropped; the map still works.
    previewTask.mockRejectedValue(new Error('no preview'))
    await typeAnOrder()
    expect((screen.getByRole('button', { name: say.assistant.approve }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(new RegExp(say.assistant.noChecks.slice(0, 40)))).toBeTruthy()
    expect(onProposal).toHaveBeenCalledWith(null)
    fireEvent.click(screen.getByRole('button', { name: say.assistant.decline }))
    await waitFor(() => expect(confirm).toHaveBeenCalledWith('tok', 'X1', false))
  })
})

describe('a question', () => {
  it('shows the answer and proposes nothing', async () => {
    sayText.mockResolvedValue({
      ...orderExchange(),
      kind: 'question',
      needs_confirmation: false,
      action: null,
      spoken: 'Tessy is standing by at the gate.',
    })
    renderPanel()
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveProperty('disabled', true))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'where is Tessy' } })
    fireEvent.submit(screen.getByRole('textbox').closest('form')!)
    await waitFor(() => expect(screen.getByText('Tessy is standing by at the gate.')).toBeTruthy())
    expect(previewTask).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: say.assistant.approve })).toBeNull()
  })
})

describe('when the assistant cannot be reached', () => {
  it('says so and takes no orders', async () => {
    capabilities.mockRejectedValue(new Error('down'))
    renderPanel()
    await waitFor(() => expect(screen.getByText(say.assistant.unreachable)).toBeTruthy())
    expect((screen.getByRole('textbox') as HTMLInputElement).disabled).toBe(true)
  })
})

describe('what the panel claims to know', () => {
  // The request carries the operator's words and nothing else, so the
  // panel must not suggest it was told what the operator is looking at.
  it('shows no "looking at" strip and names no machine before the server does', async () => {
    const { container } = renderPanel()
    await waitFor(() => expect(screen.getByRole('textbox')).not.toHaveProperty('disabled', true))
    expect(container.querySelector('.looking')).toBeNull()
    expect(screen.queryByText(/Looking at/i)).toBeNull()
    expect((screen.getByRole('textbox') as HTMLInputElement).placeholder).toBe(say.assistant.placeholder)
  })
})

describe('reaching the voice service', () => {
  it('tells the screen it is unreachable, then tells it again when the service answers', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const onReach = vi.fn()
    capabilities.mockRejectedValueOnce(new Error('down'))
    renderPanel({ onReach })
    await waitFor(() => expect(onReach).toHaveBeenLastCalledWith(false))
    await act(() => vi.advanceTimersByTimeAsync(VOICE_RETRY_MS))
    await waitFor(() => expect(onReach).toHaveBeenLastCalledWith(true))
    expect(onReach).toHaveBeenCalledTimes(2)
  })

  it('reports the same silence once, so a panel opened by hand stays open', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const onReach = vi.fn()
    capabilities.mockRejectedValue(new Error('down'))
    renderPanel({ onReach })
    await waitFor(() => expect(onReach).toHaveBeenCalledWith(false))
    // One retry per pause; React renders between them.
    for (let i = 0; i < 3; i++) await act(() => vi.advanceTimersByTimeAsync(VOICE_RETRY_MS))
    expect(capabilities).toHaveBeenCalledTimes(4)
    expect(onReach).toHaveBeenCalledTimes(1)
  })

  it('says why on the collapsed rail', async () => {
    capabilities.mockRejectedValue(new Error('down'))
    renderPanel({ collapsed: true })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: say.assistant.unreachable }).getAttribute('title')).toBe(
        say.assistant.unreachable,
      ),
    )
  })
})
