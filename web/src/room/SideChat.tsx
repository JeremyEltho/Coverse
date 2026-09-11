import { useEffect, useRef, useState } from 'react'
import type { SideMessage } from '../lib/types'

interface SideChatProps {
  messages: SideMessage[]
  isDriver: boolean
  onSay: (body: string) => void
  onPromote: (id: string) => void
  onQueue: (body: string) => void
}

/**
 * The human backchannel.
 *
 * The assistant never sees any of this, which is the point: you can say an idea
 * is a dead end without the model reading it over your shoulder. A line only
 * reaches the model when someone deliberately pushes it across.
 */
export function SideChat({ messages, isDriver, onSay, onPromote, onQueue }: SideChatProps) {
  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = scrollRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [messages])

  const submit = () => {
    const body = draft.trim()
    if (!body) return
    onSay(body)
    setDraft('')
  }

  return (
    <div className="panel">
      <p className="panel-note">Private to the people here. The assistant never sees it.</p>

      <div className="panel-scroll" ref={scrollRef}>
        {messages.length === 0 ? (
          <p className="panel-empty">Talk amongst yourselves.</p>
        ) : (
          messages.map((message) => (
            <div key={message.id} className="side-line">
              <span className="side-author">{message.author_name}</span>
              <span className="side-body">{message.body}</span>
              <span className="side-actions">
                {isDriver ? (
                  <button type="button" className="ghost" onClick={() => onPromote(message.id)}>
                    Ask this
                  </button>
                ) : (
                  <button type="button" className="ghost" onClick={() => onQueue(message.body)}>
                    Queue it
                  </button>
                )}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="panel-composer">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              submit()
            }
          }}
          placeholder="Say something to the room"
        />
      </div>
    </div>
  )
}
