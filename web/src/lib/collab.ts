/**
 * The Yjs connection for one room.
 *
 * This single document carries everything shared: the thread, side chat, queue,
 * the draft everyone types into, pins and the baton. One replica per tab.
 */
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import { wsUrl } from './origin'
import type { Peer, QueueItem, SideMessage } from './types'

export interface RoomSession {
  doc: Y.Doc
  provider: WebsocketProvider
  messages: Y.Array<Y.Map<unknown>>
  sidechat: Y.Array<SideMessage>
  queue: Y.Array<QueueItem>
  composer: Y.Text
  pins: Y.Map<unknown>
  control: Y.Map<unknown>
  destroy: () => void
}

export function connect(
  code: string,
  memberId: string,
  name: string,
  color: string,
): RoomSession {
  const doc = new Y.Doc()

  const provider = new WebsocketProvider(wsUrl('/ws/room'), code, doc, {
    params: { member: memberId },
    connect: true,
  })

  provider.awareness.setLocalStateField('user', { name, color, memberId })

  return {
    doc,
    provider,
    messages: doc.getArray('messages'),
    sidechat: doc.getArray<SideMessage>('sidechat'),
    queue: doc.getArray<QueueItem>('queue'),
    composer: doc.getText('composer'),
    pins: doc.getMap('pins'),
    control: doc.getMap('control'),
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
    const user = (state as { user?: Peer }).user
    if (!user?.name) return
    peers.push({
      clientId,
      memberId: user.memberId,
      name: user.name,
      color: user.color,
      isAI: user.isAI,
    })
  })
  return peers
}
