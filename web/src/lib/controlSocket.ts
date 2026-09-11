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
  | { type: 'queue'; body: string }
  | { type: 'fork'; job: string; body: string; history: { role: string; content: string }[] }
  | { type: 'ping' }

type Listener = (event: ControlEvent) => void

export class ControlSocket {
  private socket: WebSocket | null = null
  private listeners = new Set<Listener>()
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

    socket.onclose = () => {
      if (this.closed) return
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

  send(message: ControlMessage): void {
    const payload = JSON.stringify(message)
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(payload)
    else this.pending.push(payload)
  }

  destroy(): void {
    this.closed = true
    if (this.timer) window.clearTimeout(this.timer)
    this.listeners.clear()
    this.socket?.close()
  }
}

export function newJobId(): string {
  return Math.random().toString(36).slice(2, 10)
}
