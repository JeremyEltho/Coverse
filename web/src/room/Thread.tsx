import { useEffect, useRef } from 'react'
import type { Member, ThreadMessage } from '../lib/types'
import { Sprite } from '../sprites/Sprite'
import { ASSISTANT_SPRITE } from '../sprites/catalogue'
import { Markdown } from './Markdown'

interface ThreadProps {
  messages: ThreadMessage[]
  members: Member[]
  pins: string[]
  memberId: string
  onPin: (id: string) => void
  onReact: (id: string, emoji: string) => void
}

const QUICK_REACTIONS = ['👍', '🔥', '🤔']

/** The shared conversation. Everyone sees this, including replies arriving. */
export function Thread({ messages, members, pins, memberId, onPin, onReact }: ThreadProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const pinnedAtBottom = useRef(true)

  // Follow the stream, but stop hijacking the scroll if someone scrolled up.
  useEffect(() => {
    const element = scrollRef.current
    if (element && pinnedAtBottom.current) element.scrollTop = element.scrollHeight
  }, [messages])

  const onScroll = () => {
    const element = scrollRef.current
    if (!element) return
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight
    pinnedAtBottom.current = distance < 80
  }

  if (messages.length === 0) {
    return (
      <div className="thread is-empty" ref={scrollRef}>
        <div className="thread-empty">
          <h2>Nobody has asked anything yet</h2>
          <p>
            Whoever holds the mic can type below. Everyone else watches the reply
            arrive, talks in the side chat, and drops suggestions in the queue.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="thread" ref={scrollRef} onScroll={onScroll}>
      {messages.map((message) => (
        <article key={message.id} className={`turn is-${message.role}`}>
          <header>
            {message.role === 'assistant' ? (
              <Sprite def={ASSISTANT_SPRITE} size={22} state={message.done ? 'idle' : 'thinking'} />
            ) : (
              <Sprite
                id={members.find((m) => m.id === message.author)?.sprite}
                size={22}
                state="idle"
              />
            )}
            <span className="turn-author">
              {message.role === 'assistant' ? 'Assistant' : message.authorName}
            </span>
            {message.shared ? (
              <span className="turn-shared" title="Brought in from a private thread">
                shared privately
              </span>
            ) : null}
            {pins.includes(message.id) ? <span className="turn-pinned">pinned</span> : null}
          </header>

          <div className="turn-body">
            {message.role === 'assistant' ? (
              <Markdown>{message.body}</Markdown>
            ) : (
              message.body
            )}
            {message.role === 'assistant' && !message.done ? (
              <span className="caret" />
            ) : null}
          </div>

          <footer className="turn-actions">
            {QUICK_REACTIONS.map((emoji) => {
              const holders = message.reactions[emoji] ?? []
              return (
                <button
                  key={emoji}
                  type="button"
                  className={`reaction${holders.includes(memberId) ? ' is-mine' : ''}`}
                  onClick={() => onReact(message.id, emoji)}
                >
                  {emoji}
                  {holders.length ? <span>{holders.length}</span> : null}
                </button>
              )
            })}
            <button type="button" className="reaction" onClick={() => onPin(message.id)}>
              {pins.includes(message.id) ? 'Unpin' : 'Pin'}
            </button>
          </footer>
        </article>
      ))}
    </div>
  )
}
