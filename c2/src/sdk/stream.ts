/**
 * The live stream.
 *
 * The socket opens with a full snapshot, so the map can draw the whole
 * picture without a second round of requests. After that it is a sequence
 * of small envelopes.
 *
 * The disconnection law applies to us as well as to the machines: losing
 * the stream must never look like the world stopped. The connection state
 * is reported to the application so the interface can say, in words, that
 * it is no longer hearing from the site, rather than quietly showing stale
 * positions as though they were current.
 */

import type { Envelope } from './types'
import { savedToken, signOut } from './session'

export type Link = 'connecting' | 'good' | 'lost'

/** The server's close code for a token it does not accept (track/api.py). */
export const CLOSE_NOT_SIGNED_IN = 4401

export interface StreamHandlers {
  onEnvelope: (envelope: Envelope) => void
  onLink: (link: Link) => void
}

export function openStream({ onEnvelope, onLink }: StreamHandlers): () => void {
  let socket: WebSocket | null = null
  let retry: number | undefined
  let closedByUs = false
  let backoffMs = 1000

  const connect = () => {
    onLink('connecting')
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
    // A browser cannot set headers when opening a WebSocket, so the token
    // travels as a query parameter. The server applies the same tokens and
    // the same roles as on every other interface.
    const token = savedToken()
    const url = `${scheme}://${location.host}/v1/stream?token=${encodeURIComponent(token)}`
    socket = new WebSocket(url)

    socket.onopen = () => {
      backoffMs = 1000
      onLink('good')
    }

    socket.onmessage = (message) => {
      try {
        onEnvelope(JSON.parse(message.data) as Envelope)
      } catch {
        // A malformed envelope is dropped, but the stream stays open: one
        // bad message must not blind the operator to the next good one.
      }
    }

    socket.onclose = (event) => {
      if (closedByUs) return
      if (event.code === CLOSE_NOT_SIGNED_IN) {
        // Not a link failure: the site is there and refused our token.
        // Retrying would only be refused again, and calling it "site link
        // lost" would be untrue. The session ends; the shell shows sign-in.
        closedByUs = true
        signOut(token)
        return
      }
      onLink('lost')
      // Keep trying, slower each time, because a site link comes back.
      retry = window.setTimeout(connect, backoffMs)
      backoffMs = Math.min(backoffMs * 2, 15000)
    }

    socket.onerror = () => socket?.close()
  }

  connect()

  return () => {
    closedByUs = true
    window.clearTimeout(retry)
    socket?.close()
  }
}
