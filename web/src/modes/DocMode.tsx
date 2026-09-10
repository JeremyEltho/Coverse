/**
 * Doc mode: a Google-Docs-style editor where the AI is another participant.
 *
 * The document is the primary surface. The AI writes into it directly when
 * asked, proposes rewrites and comments through the rail, and appears as a
 * cursor alongside the humans while it works.
 */
import { useState } from 'react'
import type { Editor } from '@tiptap/react'
import { Editor as CollaborativeEditor } from '../editor/Editor'
import { Toolbar } from '../editor/Toolbar'
import { Presence } from '../components/Presence'
import { SuggestionRail } from '../components/SuggestionRail'
import { ChatPanel } from '../components/ChatPanel'
import type { useDocumentSession } from '../hooks/useDocumentSession'
import type { Session } from '../lib/auth'

interface DocModeProps {
  documentId: string
  session: Session
  state: ReturnType<typeof useDocumentSession>
}

export function DocMode({ session, state }: DocModeProps) {
  const [editor, setEditor] = useState<Editor | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  if (!state.collab) return <div className="editor-loading">Connecting…</div>

  return (
    <div className={`mode doc-mode${sidebarOpen ? ' with-sidebar' : ''}`}>
      <div className="doc-bar">
        <Toolbar editor={editor} />
        <div className="doc-bar-right">
          <Presence peers={state.peers} connected={state.connected} />
          <button
            type="button"
            className="secondary"
            onClick={() => setSidebarOpen((open) => !open)}
          >
            {sidebarOpen ? 'Hide assistant' : 'Assistant'}
          </button>
        </div>
      </div>

      <div className="doc-body">
        <main className="doc-canvas">
          <CollaborativeEditor
            doc={state.collab.doc}
            provider={state.collab.provider}
            name={session.name}
            color={state.color}
            suggestions={state.suggestions}
            activeSuggestionId={state.activeSuggestionId}
            onEditorReady={(instance) => {
              setEditor(instance ?? null)
              state.setEditor(instance ?? null)
            }}
            onRewrite={(selection) => state.selectionAction('rewrite', selection)}
            onComment={(selection) => state.selectionAction('comment', selection)}
            onAsk={(selection) => {
              setSidebarOpen(true)
              state.ask(`About this passage: “${selection}”`)
            }}
          />
        </main>

        <SuggestionRail
          suggestions={state.suggestions}
          activeId={state.activeSuggestionId}
          staleIds={state.staleIds}
          onFocus={state.setActiveSuggestionId}
          onAccept={state.acceptSuggestion}
          onReject={state.rejectSuggestion}
        />

        {sidebarOpen ? (
          <ChatPanel
            title="Assistant"
            subtitle={state.modelLabel}
            turns={state.turns}
            busy={state.busy}
            placeholder="Ask about the document, or tell the assistant what to write into it."
            onSend={(prompt) => state.generate(prompt)}
            onCancel={state.cancel}
          />
        ) : null}
      </div>
    </div>
  )
}
