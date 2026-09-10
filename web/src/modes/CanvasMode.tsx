/**
 * Canvas mode: conversation on the left, the document it produces on the right.
 *
 * Same document, same CRDT, same sockets as Doc mode -- only the layout and the
 * default action differ. The document stays collaborative and editable by hand
 * while the conversation drives it.
 */
import { useState } from 'react'
import type { Editor } from '@tiptap/react'
import { Editor as CollaborativeEditor } from '../editor/Editor'
import { Toolbar } from '../editor/Toolbar'
import { Presence } from '../components/Presence'
import { ChatPanel } from '../components/ChatPanel'
import type { useDocumentSession } from '../hooks/useDocumentSession'
import type { Session } from '../lib/auth'

interface CanvasModeProps {
  documentId: string
  session: Session
  state: ReturnType<typeof useDocumentSession>
}

export function CanvasMode({ session, state }: CanvasModeProps) {
  const [editor, setEditor] = useState<Editor | null>(null)

  if (!state.collab) return <div className="editor-loading">Connecting…</div>

  return (
    <div className="mode canvas-mode">
      <ChatPanel
        title="Conversation"
        subtitle={state.modelLabel}
        turns={state.turns}
        busy={state.busy}
        placeholder="Describe the document you want. The assistant builds it on the right, and you can edit it by hand at any time."
        onSend={(prompt) => state.canvas(prompt)}
        onCancel={state.cancel}
      />

      <div className="canvas-document">
        <div className="doc-bar">
          <Toolbar editor={editor} />
          <Presence peers={state.peers} connected={state.connected} />
        </div>
        <main className="doc-canvas">
          <CollaborativeEditor
            doc={state.collab.doc}
            provider={state.collab.provider}
            name={session.name}
            color={state.color}
            suggestions={state.suggestions}
            activeSuggestionId={state.activeSuggestionId}
            placeholder="The document the assistant builds will appear here. You can edit it directly."
            onEditorReady={(instance) => {
              setEditor(instance ?? null)
              state.setEditor(instance ?? null)
            }}
            onRewrite={(selection) => state.selectionAction('rewrite', selection)}
            onComment={(selection) => state.selectionAction('comment', selection)}
            onAsk={(selection) => state.ask(`About this passage: “${selection}”`)}
          />
        </main>
      </div>
    </div>
  )
}
