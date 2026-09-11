import type * as Y from 'yjs'
import { useSharedText } from '../hooks/useSharedText'

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
}: ComposerProps) {
  const { ref, value, onInput } = useSharedText(text)

  const submit = () => {
    if (!isDriver || streaming) return
    const body = value.trim()
    if (body) onSend(body)
  }

  return (
    <div className="composer">
      <div className="composer-shell glass glass-strong">
        <textarea
          ref={ref}
          value={value}
          onChange={(event) => onInput(event.target.value)}
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
