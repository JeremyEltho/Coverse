/**
 * The control socket.
 *
 * Commands go out, and almost nothing comes back: the AI's reply lands in the
 * shared document and arrives over the Yjs socket instead. What does come back
 * are errors, readiness, and the deltas of a private fork, which is the one
 * thing that is not shared state.
 */
import { wsUrl } from './origin'

export interface ControlEvent {
  type: 'ready' | 'error' | 'pong' | 'status' | 'delta' | 'done'
  scope?: 'fork'
  job?: string
  error?: string
  text?: string
  answer?: string
  provider?: string
  model?: string
  is_driver?: boolean
  member_id?: string
}

export type ControlMessage =
  | { type: 'send'; body: string }
  | { type: 'send_queued'; id: string }
  | { type: 'stop' }
  | { type: 'request_mic' }
  | { type: 'withdraw_request' }
  | { type: 'grant_mic'; member: string }
  | { type: 'release_mic' }
  | { type: 'sidechat'; body: string }
  | { type: 'promote'; id: string }
  | { type: 'share_fork'; question: string; answer: string }
  | { type: 'queue'; body: string }
  | { type: 'fork'; job: string; body: string; history: { role: string; content: string }[] }
  | { type: 'ping' }

type Listener = (event: ControlEvent) => void
type FatalListener = (reason: FatalReason) => void

/**
 * Why a socket stopped for good.
 *
 * The server closes with these rather than dropping the connection, so the
 * difference between "the network blinked" and "this room no longer exists" is
 * knowable. Retrying the second one forever would leave people staring at
 * "reconnecting" for a room that is never coming back.
 */
export type FatalReason = 'room-gone' | 'not-a-member'

const WS_UNAUTHORIZED = 4401
const WS_NOT_FOUND = 4404

export class ControlSocket {
  private socket: WebSocket | null = null
  private listeners = new Set<Listener>()
  private fatalListeners = new Set<FatalListener>()
  private pending: string[] = []
  private closed = false
  private attempt = 0
  private timer: number | null = null

  constructor(
    private readonly code: string,
    private readonly memberId: string,
  ) {
    this.open()
  }

  private open(): void {
    if (this.closed) return

    const socket = new WebSocket(
      wsUrl(`/ws/control/${this.code}?member=${encodeURIComponent(this.memberId)}`),
    )
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      for (const message of this.pending.splice(0)) socket.send(message)
    }

    socket.onmessage = (event) => {
      let parsed: ControlEvent
      try {
        parsed = JSON.parse(event.data as string) as ControlEvent
      } catch {
        return
      }
      for (const listener of this.listeners) listener(parsed)
    }

    socket.onclose = (event) => {
      if (this.closed) return

      if (event.code === WS_NOT_FOUND || event.code === WS_UNAUTHORIZED) {
        this.closed = true
        const reason: FatalReason =
          event.code === WS_NOT_FOUND ? 'room-gone' : 'not-a-member'
        for (const listener of this.fatalListeners) listener(reason)
        return
      }

      const delay = Math.min(1000 * 2 ** this.attempt, 15000)
      this.attempt += 1
      this.timer = window.setTimeout(() => this.open(), delay)
    }

    socket.onerror = () => socket.close()
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  onFatal(listener: FatalListener): () => void {
    this.fatalListeners.add(listener)
    return () => this.fatalListeners.delete(listener)
  }

  send(message: ControlMessage): void {
    const payload = JSON.stringify(message)
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(payload)
    else this.pending.push(payload)
  }

  destroy(): void {
    this.closed = true
    if (this.timer) window.clearTimeout(this.timer)
    this.listeners.clear()
    this.fatalListeners.clear()
    this.socket?.close()
  }
}

export function newJobId(): string {
  return Math.random().toString(36).slice(2, 10)
}
