import { useState } from 'react'
import type { ForkTurn } from '../lib/types'
import { Markdown } from './Markdown'

interface ForkPanelProps {
  turns: ForkTurn[]
  busy: boolean
  isDriver: boolean
  onAsk: (body: string) => void
  onShare: (content: string) => void
}

/**
 * A private question, with the room's thread as context.
 *
 * For the person who wants to check something without taking the mic or
 * derailing everyone. Nothing here is visible to the room until it is shared,
 * which sends it if you have the mic and queues it if you do not.
 */
export function ForkPanel({ turns, busy, isDriver, onAsk, onShare }: ForkPanelProps) {
  const [draft, setDraft] = useState('')

  const submit = () => {
    const body = draft.trim()
    if (!body || busy) return
    onAsk(body)
    setDraft('')
  }

  return (
    <div className="panel">
      <p className="panel-note">
        Only you see this. It knows the room&rsquo;s conversation so far.
      </p>

      <div className="panel-scroll">
        {turns.length === 0 ? (
          <p className="panel-empty">
            Ask something without interrupting. Share the answer if it turns out to matter.
          </p>
        ) : (
          turns.map((turn, index) => (
            <div key={index} className={`fork-turn is-${turn.role}`}>
              <span className="fork-role">{turn.role === 'user' ? 'You' : 'Assistant'}</span>
              <div className="fork-body">
                {turn.role === 'assistant' ? (
                  <Markdown>{turn.content}</Markdown>
                ) : (
                  <p>{turn.content}</p>
                )}
                {turn.streaming ? <span className="caret" /> : null}
              </div>
              {turn.role === 'assistant' && !turn.streaming && turn.content ? (
                <button type="button" className="ghost" onClick={() => onShare(turn.content)}>
                  {isDriver ? 'Ask the room this' : 'Add to queue'}
                </button>
              ) : null}
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
          placeholder={busy ? 'Thinking…' : 'Ask just for yourself'}
          disabled={busy}
        />
      </div>
    </div>
  )
}
