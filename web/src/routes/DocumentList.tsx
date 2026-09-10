import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Session } from '../lib/auth'
import type { DocumentMode, DocumentSummary } from '../lib/types'
import { signOut } from '../lib/auth'

export function DocumentList({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const refresh = () => {
    setLoading(true)
    api
      .listDocuments(session.token)
      .then(setDocuments)
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false))
  }

  useEffect(refresh, [session.token])

  const create = async (mode: DocumentMode) => {
    try {
      const document = await api.createDocument(session.token, 'Untitled', mode)
      navigate(`/d/${document.id}?mode=${mode}`)
    } catch (cause) {
      setError((cause as Error).message)
    }
  }

  const remove = async (id: string) => {
    await api.deleteDocument(session.token, id).catch(() => undefined)
    refresh()
  }

  return (
    <div className="page">
      <header className="app-header">
        <span className="brand">Coverse</span>
        <div className="app-header-right">
          <span className="who">{session.name}</span>
          <button
            type="button"
            className="secondary"
            onClick={async () => {
              await signOut()
              onSignOut()
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="list-main">
        <div className="list-intro">
          <h1>Your documents</h1>
          <p>
            A collaborative editor with an assistant in the room. Open a document with
            other people and watch edits, cursors and AI writing land live.
          </p>
          <div className="list-actions">
            <button type="button" onClick={() => create('doc')}>
              New document
            </button>
            <button type="button" className="secondary" onClick={() => create('canvas')}>
              New canvas
            </button>
          </div>
        </div>

        {error ? <p className="error-banner">{error}</p> : null}

        {loading ? (
          <p className="muted">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="muted">No documents yet. Create one to get started.</p>
        ) : (
          <ul className="doc-list">
            {documents.map((document) => (
              <li key={document.id}>
                <button
                  type="button"
                  className="doc-card"
                  onClick={() => navigate(`/d/${document.id}?mode=${document.mode}`)}
                >
                  <span className="doc-card-title">{document.title || 'Untitled'}</span>
                  <span className="doc-card-meta">
                    {document.mode === 'canvas' ? 'Canvas' : 'Document'} ·{' '}
                    {new Date(document.updated_at).toLocaleString()}
                  </span>
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => remove(document.id)}
                  aria-label={`Delete ${document.title}`}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
