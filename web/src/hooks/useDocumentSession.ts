/**
 * Everything one open document needs: the CRDT connection, the chat socket,
 * presence, suggestions and AI actions.
 *
 * Both modes use this, which is what makes them two faces of one product rather
 * than two applications that happen to share a repo.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Editor } from '@tiptap/react'
import { connect, colorFor, readPeers, type CollabSession } from '../lib/collab'
import { ChatSocket, newJobId, type ServerEvent } from '../lib/chatSocket'
import { captureAnchor, captureSelection, resolveSelection } from '../editor/relpos'
import type { AiAction, ChatTurn, Peer, Suggestion } from '../lib/types'
import type { Session } from '../lib/auth'

interface Options {
  documentId: string
  session: Session
}

export function useDocumentSession({ documentId, session }: Options) {
  const [collab, setCollab] = useState<CollabSession | null>(null)
  const [peers, setPeers] = useState<Peer[]>([])
  const [connected, setConnected] = useState(false)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [activeSuggestionId, setActiveSuggestionId] = useState<string | null>(null)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [busy, setBusy] = useState(false)
  const [modelLabel, setModelLabel] = useState('')

  const chatRef = useRef<ChatSocket | null>(null)
  const editorRef = useRef<Editor | null>(null)
  const jobRef = useRef<string | null>(null)

  // --- CRDT connection ---------------------------------------------------------

  useEffect(() => {
    const instance = connect(documentId, session.token, session.name)
    setCollab(instance)

    const syncPeers = () => setPeers(readPeers(instance.provider))
    const onStatus = (event: { status: string }) => setConnected(event.status === 'connected')

    instance.provider.awareness.on('change', syncPeers)
    instance.provider.on('status', onStatus)
    syncPeers()

    const readSuggestions = () =>
      setSuggestions(
        Array.from(instance.suggestions.values())
          .filter((s) => s && s.status === 'pending')
          .sort((a, b) => a.created_at - b.created_at),
      )
    instance.suggestions.observe(readSuggestions)
    readSuggestions()

    return () => {
      instance.provider.awareness.off('change', syncPeers)
      instance.provider.off('status', onStatus)
      instance.suggestions.unobserve(readSuggestions)
      instance.destroy()
      setCollab(null)
      setConnected(false)
    }
  }, [documentId, session.token, session.name])

  // --- chat socket -------------------------------------------------------------

  useEffect(() => {
    const socket = new ChatSocket(documentId, session.token)
    chatRef.current = socket

    const unsubscribe = socket.on((event: ServerEvent) => {
      switch (event.type) {
        case 'ready':
          setModelLabel(`${event.provider ?? ''} · ${event.model ?? ''}`)
          if (event.history?.length) {
            setTurns(
              event.history.map((entry) => ({
                id: `h${entry.id}`,
                role: entry.role,
                content: entry.content,
              })),
            )
          }
          break

        case 'delta':
          setTurns((current) => appendDelta(current, event.text ?? ''))
          break

        case 'done':
          setBusy(false)
          jobRef.current = null
          setTurns((current) => current.map((turn) => ({ ...turn, streaming: false })))
          break

        case 'cancelled':
          setBusy(false)
          jobRef.current = null
          setTurns((current) =>
            current.map((turn) =>
              turn.streaming ? { ...turn, streaming: false, content: `${turn.content} (stopped)` } : turn,
            ),
          )
          break

        case 'error':
          setBusy(false)
          jobRef.current = null
          setTurns((current) => [
            ...current.map((turn) => ({ ...turn, streaming: false })),
            {
              id: newJobId(),
              role: 'assistant',
              content: event.error ?? 'Something went wrong.',
              error: true,
            },
          ])
          break

        default:
          break
      }
    })

    return () => {
      unsubscribe()
      socket.destroy()
      chatRef.current = null
    }
  }, [documentId, session.token])

  // --- actions -----------------------------------------------------------------

  const run = useCallback(
    (action: AiAction, payload: Record<string, unknown>, echo?: string) => {
      const socket = chatRef.current
      if (!socket) return

      const job = newJobId()
      jobRef.current = job
      setBusy(true)

      if (echo !== undefined) {
        setTurns((current) => [
          ...current,
          { id: `${job}-u`, role: 'user', content: echo },
          { id: `${job}-a`, role: 'assistant', content: '', streaming: true },
        ])
      } else {
        setTurns((current) => [
          ...current,
          { id: `${job}-a`, role: 'assistant', content: '', streaming: true },
        ])
      }

      socket.send({ type: action, job, ...payload } as never)
    },
    [],
  )

  const history = useMemo(
    () => turns.filter((t) => !t.error).map((t) => ({ role: t.role, content: t.content })),
    [turns],
  )

  const generate = useCallback((prompt: string) => run('generate', { prompt }, prompt), [run])

  const canvas = useCallback(
    (prompt: string) => run('canvas', { prompt, history }, prompt),
    [run, history],
  )

  const ask = useCallback(
    (prompt: string) => run('ask', { prompt, history }, prompt),
    [run, history],
  )

  /** Selection actions capture a relative position so the anchor survives edits. */
  const selectionAction = useCallback(
    (action: 'rewrite' | 'comment', selection: string, instruction = '') => {
      const editor = editorRef.current
      if (!editor) return
      run(
        action,
        {
          selection,
          instruction,
          relpos: captureSelection(editor) ?? undefined,
          anchor: captureAnchor(editor),
        },
        action === 'rewrite' ? `Rewrite: “${selection}”` : `Review: “${selection}”`,
      )
    },
    [run],
  )

  const cancel = useCallback(() => {
    const job = jobRef.current
    if (job) chatRef.current?.cancel(job)
  }, [])

  // --- suggestion resolution ---------------------------------------------------

  /**
   * Suggestions whose anchored text no longer resolves. Applying one of these
   * would edit the wrong range, so the UI disables them instead.
   */
  const staleIds = useMemo(() => {
    const editor = editorRef.current
    const stale = new Set<string>()
    if (!editor) return stale
    for (const suggestion of suggestions) {
      if (!suggestion.relpos || !resolveSelection(editor, suggestion.relpos)) {
        stale.add(suggestion.id)
      }
    }
    return stale
  }, [suggestions])

  const acceptSuggestion = useCallback(
    (suggestion: Suggestion) => {
      const editor = editorRef.current
      if (!editor || !suggestion.relpos || !suggestion.replacement) return

      const range = resolveSelection(editor, suggestion.relpos)
      if (!range) return

      // Applying through TipTap makes it an ordinary CRDT edit: it merges with
      // concurrent typing and lands in undo history like anything else.
      editor
        .chain()
        .focus()
        .insertContentAt({ from: range.from, to: range.to }, suggestion.replacement)
        .run()

      collab?.suggestions.delete(suggestion.id)
    },
    [collab],
  )

  const rejectSuggestion = useCallback(
    (suggestion: Suggestion) => {
      collab?.suggestions.delete(suggestion.id)
    },
    [collab],
  )

  const setEditor = useCallback((editor: Editor | null) => {
    editorRef.current = editor
  }, [])

  return {
    collab,
    peers,
    connected,
    suggestions,
    staleIds,
    activeSuggestionId,
    setActiveSuggestionId,
    turns,
    busy,
    modelLabel,
    color: colorFor(session.name),
    setEditor,
    generate,
    canvas,
    ask,
    selectionAction,
    cancel,
    acceptSuggestion,
    rejectSuggestion,
  }
}

function appendDelta(turns: ChatTurn[], text: string): ChatTurn[] {
  const index = turns.findIndex((turn) => turn.streaming)
  if (index === -1) return turns
  const next = [...turns]
  next[index] = { ...next[index], content: next[index].content + text }
  return next
}
