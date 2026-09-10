import { useEffect, useRef, useState } from 'react'
import type { ChatTurn } from '../lib/types'

interface ChatPanelProps {
  turns: ChatTurn[]
  busy: boolean
  placeholder: string
  title: string
  subtitle?: string
  onSend: (prompt: string) => void
  onCancel: () => void
}

export function ChatPanel({
  turns,
  busy,
  placeholder,
  title,
  subtitle,
  onSend,
  onCancel,
}: ChatPanelProps) {
  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = scrollRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [turns])

  const submit = () => {
    const prompt = draft.trim()
    if (!prompt || busy) return
    onSend(prompt)
    setDraft('')
  }

  return (
    <section className="chat-panel">
      <header className="chat-header">
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </header>

      <div className="chat-scroll" ref={scrollRef}>
        {turns.length === 0 ? (
          <p className="chat-empty">{placeholder}</p>
        ) : (
          turns.map((turn) => (
            <article
              key={turn.id}
              className={`chat-turn is-${turn.role}${turn.error ? ' is-error' : ''}`}
            >
              <span className="chat-role">{turn.role === 'user' ? 'You' : 'Assistant'}</span>
              <div className="chat-body">
                {turn.content}
                {turn.streaming ? <span className="caret" /> : null}
              </div>
            </article>
          ))
        )}
      </div>

      <footer className="chat-composer">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder="Ask, or describe what to write. Enter to send."
          rows={3}
        />
        {busy ? (
          <button type="button" className="secondary" onClick={onCancel}>
            Stop
          </button>
        ) : (
          <button type="button" onClick={submit} disabled={!draft.trim()}>
            Send
          </button>
        )}
      </footer>
    </section>
  )
}
