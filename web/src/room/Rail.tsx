import { useState } from 'react'
import type { ForkTurn, QueueItem, RailTab, SideMessage, ThreadMessage } from '../lib/types'
import { SideChat } from './SideChat'
import { Queue } from './Queue'
import { Pins } from './Pins'
import { ForkPanel } from './ForkPanel'

interface RailProps {
  sidechat: SideMessage[]
  queue: QueueItem[]
  messages: ThreadMessage[]
  pins: string[]
  isDriver: boolean
  forkTurns: ForkTurn[]
  forkBusy: boolean
  roomCode: string
  onSay: (body: string) => void
  onPromote: (id: string) => void
  onQueue: (body: string) => void
  onSendQueued: (id: string) => void
  onDropQueued: (id: string) => void
  onUnpin: (id: string) => void
  onAskPrivately: (body: string) => void
  onShareFork: (question: string, answer: string) => void
}

const TABS: { id: RailTab; label: string }[] = [
  { id: 'chat', label: 'Side chat' },
  { id: 'queue', label: 'Queue' },
  { id: 'pins', label: 'Pins' },
  { id: 'fork', label: 'Just me' },
]

export function Rail(props: RailProps) {
  const [tab, setTab] = useState<RailTab>('chat')

  const counts: Record<RailTab, number> = {
    chat: props.sidechat.length,
    queue: props.queue.length,
    pins: props.pins.length,
    fork: props.forkTurns.filter((t) => t.role === 'assistant').length,
  }

  return (
    <aside className="rail">
      <nav className="rail-tabs" role="tablist">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            className={tab === entry.id ? 'is-active' : ''}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
            {counts[entry.id] ? <span className="badge">{counts[entry.id]}</span> : null}
          </button>
        ))}
      </nav>

      <div className="rail-body">
        {tab === 'chat' ? (
          <SideChat
            messages={props.sidechat}
            isDriver={props.isDriver}
            onSay={props.onSay}
            onPromote={props.onPromote}
            onQueue={props.onQueue}
          />
        ) : null}

        {tab === 'queue' ? (
          <Queue
            items={props.queue}
            isDriver={props.isDriver}
            onQueue={props.onQueue}
            onSend={props.onSendQueued}
            onDrop={props.onDropQueued}
          />
        ) : null}

        {tab === 'pins' ? (
          <Pins
            messages={props.messages}
            pins={props.pins}
            roomCode={props.roomCode}
            onUnpin={props.onUnpin}
          />
        ) : null}

        {tab === 'fork' ? (
          <ForkPanel
            turns={props.forkTurns}
            busy={props.forkBusy}
            onAsk={props.onAskPrivately}
            onShare={props.onShareFork}
          />
        ) : null}
      </div>
    </aside>
  )
}
