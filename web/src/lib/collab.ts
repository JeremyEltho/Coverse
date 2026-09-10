/**
 * The Yjs connection for one document.
 *
 * Owns the Y.Doc, the websocket provider and awareness. The editor, the
 * suggestion rail and the presence bar all read from this single instance, so
 * there is exactly one replica per document in the tab.
 */
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import type { Peer, Suggestion } from './types'

const PALETTE = ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#db2777']

export function colorFor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) | 0
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

export interface CollabSession {
  doc: Y.Doc
  provider: WebsocketProvider
  suggestions: Y.Map<Suggestion>
  destroy: () => void
}

function socketBase(): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}`
}

export function connect(documentId: string, token: string, name: string): CollabSession {
  const doc = new Y.Doc()

  const provider = new WebsocketProvider(`${socketBase()}/ws/doc`, documentId, doc, {
    params: { token },
    // y-websocket reconnects with exponential backoff on its own.
    connect: true,
  })

  provider.awareness.setLocalStateField('user', {
    name,
    color: colorFor(name),
  })

  return {
    doc,
    provider,
    suggestions: doc.getMap<Suggestion>('suggestions'),
    destroy: () => {
      provider.awareness.setLocalState(null)
      provider.destroy()
      doc.destroy()
    },
  }
}

export function readPeers(provider: WebsocketProvider): Peer[] {
  const peers: Peer[] = []
  provider.awareness.getStates().forEach((state, clientId) => {
    const user = (state as { user?: { name?: string; color?: string; isAI?: boolean } }).user
    if (!user?.name) return
    peers.push({
      clientId,
      name: user.name,
      color: user.color ?? colorFor(user.name),
      isAI: user.isAI,
    })
  })
  return peers
}
