import type * as Y from 'yjs'
import { useSharedText } from '../hooks/useSharedText'
import { Sprite } from '../sprites/Sprite'
import type { Peer } from '../lib/types'

interface ComposerProps {
  text: Y.Text | null
  isDriver: boolean
  streaming: boolean
  driverName: string | null
  onSend: (body: string) => void
  onStop: () => void
  onRequestMic: () => void
  onWithdraw: () => void
  requestPending: boolean
  onTyping: () => void
  typing: Peer[]
}

/**
 * The shared draft.
 *
 * Everyone types into the same box, which is the closest thing to leaning over
 * somebody's shoulder and fixing their wording. Only the driver can send it.
 */
export function Composer({
  text,
  isDriver,
  streaming,
  driverName,
  onSend,
  onStop,
  onRequestMic,
  onWithdraw,
  requestPending,
  onTyping,
  typing,
}: ComposerProps) {
  const { ref, value, onInput } = useSharedText(text)

  const submit = () => {
    if (!isDriver || streaming) return
    const body = value.trim()
    if (body) onSend(body)
  }

  return (
    <div className="composer">
      <div className="composer-shell">
        <textarea
          ref={ref}
          value={value}
          onChange={(event) => {
            onInput(event.target.value)
            onTyping()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          rows={2}
          placeholder={
            isDriver
              ? 'Ask the assistant…'
              : `Type here for ${driverName ?? 'the driver'} to send…`
          }
        />

        <div className="composer-actions">
          <span className="composer-typing" aria-live="polite">
            {typing.map((peer) => (
              <Sprite
                key={peer.clientId}
                id={peer.sprite}
                size={20}
                state="typing"
                title={`${peer.name} is typing`}
              />
            ))}
            {typing.length === 1 ? `${typing[0].name} is typing` : null}
            {typing.length > 1 ? `${typing.length} people typing` : null}
          </span>

          <span className="composer-hint">
            {isDriver ? (
              'Everyone can edit this. Only you can send.'
            ) : (
              <>
                <strong>{driverName ?? 'Someone else'}</strong> sends this
              </>
            )}
          </span>

          {streaming ? (
            <button type="button" className="secondary" onClick={onStop}>
              Stop
            </button>
          ) : isDriver ? (
            <button type="button" onClick={submit} disabled={!value.trim()}>
              Send
            </button>
          ) : requestPending ? (
            <button type="button" className="secondary" onClick={onWithdraw}>
              Cancel request
            </button>
          ) : (
            <button type="button" className="secondary" onClick={onRequestMic}>
              Ask for the mic
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
