import type { ThreadMessage } from '../lib/types'
import { Markdown } from './Markdown'

interface PinsProps {
  messages: ThreadMessage[]
  pins: string[]
  roomCode: string
  onUnpin: (id: string) => void
}

/**
 * The takeaway.
 *
 * Rooms are ephemeral and nothing is stored on a server, so the only way an idea
 * survives the session is if somebody exports it. The export is built here in
 * the browser from state it already has.
 */
export function Pins({ messages, pins, roomCode, onUnpin }: PinsProps) {
  const pinned = messages.filter((message) => pins.includes(message.id))

  const exportMarkdown = (onlyPinned: boolean) => {
    const source = onlyPinned ? pinned : messages
    const lines = [
      `# Coverse room ${roomCode}`,
      `_${new Date().toLocaleString()}_`,
      '',
      ...source.flatMap((message) => [
        `**${message.role === 'assistant' ? 'Assistant' : message.authorName}**`,
        '',
        message.body,
        '',
      ]),
    ]

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `coverse-${roomCode}${onlyPinned ? '-pins' : ''}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="panel">
      <p className="panel-note">
        This room disappears when everyone leaves. Export anything worth keeping.
      </p>

      <div className="panel-scroll">
        {pinned.length === 0 ? (
          <p className="panel-empty">
            Nothing pinned. Hit Pin on a reply that mattered and it collects here.
          </p>
        ) : (
          pinned.map((message) => (
            <article key={message.id} className="pin-card">
              <header>{message.role === 'assistant' ? 'Assistant' : message.authorName}</header>
              <div className="pin-body"><Markdown>{message.body}</Markdown></div>
              <footer>
                <button type="button" className="ghost" onClick={() => onUnpin(message.id)}>
                  Unpin
                </button>
              </footer>
            </article>
          ))
        )}
      </div>

      <div className="panel-composer is-buttons">
        <button type="button" onClick={() => exportMarkdown(true)} disabled={!pinned.length}>
          Export pins
        </button>
        <button type="button" className="secondary" onClick={() => exportMarkdown(false)}>
          Export all
        </button>
      </div>
    </div>
  )
}
