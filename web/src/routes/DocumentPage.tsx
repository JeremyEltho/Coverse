import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import type { Session } from '../lib/auth'
import type { DocumentMode } from '../lib/types'
import { useDocumentSession } from '../hooks/useDocumentSession'
import { DocMode } from '../modes/DocMode'
import { CanvasMode } from '../modes/CanvasMode'

export function DocumentPage({ session }: { session: Session }) {
  const { documentId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  const [title, setTitle] = useState('Untitled')
  const mode = (params.get('mode') as DocumentMode) || 'doc'

  const state = useDocumentSession({ documentId, session })

  useEffect(() => {
    let cancelled = false
    api
      .getDocument(session.token, documentId)
      .then((document) => {
        if (cancelled) return
        setTitle(document.title)
        // Honour the document's saved mode unless the URL overrides it.
        if (!params.get('mode')) setParams({ mode: document.mode }, { replace: true })
      })
      .catch(() => {
        /* the document is created on first connect in dev mode */
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, session.token])

  const rename = (next: string) => {
    setTitle(next)
    void api.updateDocument(session.token, documentId, { title: next }).catch(() => undefined)
  }

  const switchMode = (next: DocumentMode) => {
    setParams({ mode: next })
    void api.updateDocument(session.token, documentId, { mode: next }).catch(() => undefined)
  }

  return (
    <div className="page">
      <header className="app-header">
        <div className="app-header-left">
          <Link to="/" className="brand">
            Coverse
          </Link>
          <input
            className="title-input"
            value={title}
            onChange={(event) => rename(event.target.value)}
            aria-label="Document title"
          />
        </div>

        <div className="mode-toggle" role="tablist" aria-label="Mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'doc'}
            className={mode === 'doc' ? 'is-active' : ''}
            onClick={() => switchMode('doc')}
          >
            Document
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'canvas'}
            className={mode === 'canvas' ? 'is-active' : ''}
            onClick={() => switchMode('canvas')}
          >
            Canvas
          </button>
        </div>

        <div className="app-header-right">
          <button type="button" className="secondary" onClick={() => navigate('/')}>
            All documents
          </button>
        </div>
      </header>

      {mode === 'canvas' ? (
        <CanvasMode documentId={documentId} session={session} state={state} />
      ) : (
        <DocMode documentId={documentId} session={session} state={state} />
      )}
    </div>
  )
}
