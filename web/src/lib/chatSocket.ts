/**
 * The chat and control socket.
 *
 * Carries conversation and AI action requests as JSON. Document changes caused
 * by those actions do not come back through here -- they arrive over the Yjs
 * socket as CRDT updates, which is what lets every connected client see the AI
 * write in real time rather than just the person who asked.
 */
import { wsUrl } from './origin'
import type { AiAction } from './types'

export interface ServerEvent {
  type: 'ready' | 'status' | 'delta' | 'suggestion' | 'done' | 'error' | 'cancelled' | 'pong'
  job?: string
  text?: string
  error?: string
  retryable?: boolean
  action?: AiAction
  id?: string
  replacement?: string
  body?: string
  answer?: string
  provider?: string
  model?: string
  history?: { role: 'user' | 'assistant'; content: string; id: number }[]
}

export interface ChatRequest {
  type: AiAction
  job: string
  prompt?: string
  selection?: string
  instruction?: string
  relpos?: { from: string; to: string }
  anchor?: { text: string; offset: number }
  history?: { role: string; content: string }[]
}

type Listener = (event: ServerEvent) => void

export class ChatSocket {
  private socket: WebSocket | null = null
  private listeners = new Set<Listener>()
  private queue: string[] = []
  private closed = false
  private attempt = 0
  private reconnectTimer: number | null = null

  constructor(
    private readonly documentId: string,
    private readonly token: string,
  ) {
    this.open()
  }

  private open(): void {
    if (this.closed) return

    const url = wsUrl(
      `/ws/chat/${this.documentId}?token=${encodeURIComponent(this.token)}`,
    )
    const socket = new WebSocket(url)
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      for (const message of this.queue.splice(0)) socket.send(message)
    }

    socket.onmessage = (event) => {
      let parsed: ServerEvent
      try {
        parsed = JSON.parse(event.data as string) as ServerEvent
      } catch {
        return
      }
      for (const listener of this.listeners) listener(parsed)
    }

    socket.onclose = () => {
      if (this.closed) return
      // Exponential backoff, capped, so a server restart recovers on its own.
      const delay = Math.min(1000 * 2 ** this.attempt, 15000)
      this.attempt += 1
      this.reconnectTimer = window.setTimeout(() => this.open(), delay)
    }

    socket.onerror = () => socket.close()
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  send(request: ChatRequest | { type: 'cancel'; job: string } | { type: 'ping' }): void {
    const payload = JSON.stringify(request)
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(payload)
    else this.queue.push(payload)
  }

  cancel(job: string): void {
    this.send({ type: 'cancel', job })
  }

  get connected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN
  }

  destroy(): void {
    this.closed = true
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer)
    this.listeners.clear()
    this.socket?.close()
  }
}

export function newJobId(): string {
  return Math.random().toString(36).slice(2, 10)
}
