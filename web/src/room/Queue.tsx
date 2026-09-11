import { useState } from 'react'
import type { QueueItem } from '../lib/types'

interface QueueProps {
  items: QueueItem[]
  isDriver: boolean
  onQueue: (body: string) => void
  onSend: (id: string) => void
  onDrop: (id: string) => void
}

/**
 * Prompts waiting for whoever has the mic.
 *
 * This is how somebody without the mic contributes something more useful than
 * shouting. The queue belongs to the room, so it survives a handoff.
 */
export function Queue({ items, isDriver, onQueue, onSend, onDrop }: QueueProps) {
  const [draft, setDraft] = useState('')

  const submit = () => {
    const body = draft.trim()
    if (!body) return
    onQueue(body)
    setDraft('')
  }

  return (
    <div className="panel">
      <p className="panel-note">
        Anyone can add. {isDriver ? 'You can send these.' : 'The driver sends them.'}
      </p>

      <div className="panel-scroll">
        {items.length === 0 ? (
          <p className="panel-empty">Nothing queued. Add a prompt for the driver.</p>
        ) : (
          items.map((item) => (
            <article key={item.id} className="queue-card">
              <header>{item.author_name}</header>
              <p>{item.body}</p>
              <footer>
                {isDriver ? (
                  <button type="button" onClick={() => onSend(item.id)}>
                    Send
                  </button>
                ) : null}
                <button type="button" className="ghost" onClick={() => onDrop(item.id)}>
                  Remove
                </button>
              </footer>
            </article>
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
          placeholder="Suggest a prompt"
        />
      </div>
    </div>
  )
}
