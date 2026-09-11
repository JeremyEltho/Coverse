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
        rows={3}
        placeholder={
          isDriver
            ? 'Ask the assistant. Everyone can edit this box, only you can send.'
            : `Anyone can type here. ${driverName ?? 'The driver'} sends it.`
        }
      />

      <div className="composer-actions">
        <span className="composer-hint">
          {isDriver
            ? 'You have the mic'
            : `${driverName ?? 'Someone else'} has the mic`}
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
  )
}
