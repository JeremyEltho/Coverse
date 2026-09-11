/**
 * Everything one open room needs, in one hook.
 *
 * Shared state is read straight out of the Yjs document, so there is no local
 * mirror to keep in step: if it is on screen, it is what everyone else sees.
 * Only the private fork keeps React state, because it is the one thing that is
 * not shared.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type * as Y from 'yjs'
import { connect, readPeers, type RoomSession } from '../lib/collab'
import {
  ControlSocket,
  newJobId,
  type ControlEvent,
  type FatalReason,
} from '../lib/controlSocket'
import type { JoinResult } from '../lib/api'
import type {
  ForkTurn,
  MicRequest,
  Peer,
  QueueItem,
  SideMessage,
  ThreadMessage,
} from '../lib/types'

function readMessage(entry: Y.Map<unknown>): ThreadMessage {
  const reactions: Record<string, string[]> = {}
  const raw = entry.get('reactions') as Y.Map<string[]> | undefined
  raw?.forEach((holders, emoji) => {
    reactions[emoji] = [...holders]
  })

  return {
    id: String(entry.get('id')),
    role: entry.get('role') as ThreadMessage['role'],
    author: String(entry.get('author')),
    authorName: String(entry.get('author_name')),
    body: (entry.get('body') as Y.Text | undefined)?.toString() ?? '',
    at: Number(entry.get('at') ?? 0),
    done: Boolean(entry.get('done')),
    shared: Boolean(entry.get('shared')),
    reactions,
  }
}

export function useRoom(code: string, me: JoinResult) {
  const [session, setSession] = useState<RoomSession | null>(null)
  const [connected, setConnected] = useState(false)
  const [peers, setPeers] = useState<Peer[]>([])

  const [messages, setMessages] = useState<ThreadMessage[]>([])
  const [sidechat, setSidechat] = useState<SideMessage[]>([])
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [pins, setPins] = useState<string[]>([])
  const [driver, setDriver] = useState<string | null>(null)
  const [driverNameRaw, setDriverNameRaw] = useState('')
  const [model, setModelState] = useState('')
  const [requests, setRequests] = useState<MicRequest[]>([])
  const [error, setError] = useState<string | null>(null)
  const [ended, setEnded] = useState<FatalReason | null>(null)
  const [modelLabel, setModelLabel] = useState('')

  const [forkTurns, setForkTurns] = useState<ForkTurn[]>([])
  const [forkBusy, setForkBusy] = useState(false)

  const controlRef = useRef<ControlSocket | null>(null)

  // --- shared state -----------------------------------------------------------

  useEffect(() => {
    const instance = connect(code, me.member_id, me.name, me.color, setEnded)
    setSession(instance)

    const syncPeers = () => setPeers(readPeers(instance.provider))
    const onStatus = (event: { status: string }) => setConnected(event.status === 'connected')

    // Messages need a deep observer: a reply streams by mutating the Y.Text
    // inside an entry, which a shallow observer would never see.
    const readMessages = () => setMessages(instance.messages.toArray().map(readMessage))
    const readSide = () => setSidechat(instance.sidechat.toArray())
    const readQueue = () => setQueue(instance.queue.toArray())
    const readPins = () => setPins(Array.from(instance.pins.keys()))
    const readControl = () => {
      setDriver((instance.control.get('driver') as string) || null)
      setDriverNameRaw((instance.control.get('driver_name') as string) || '')
      setModelState((instance.control.get('model') as string) || '')
      setRequests(((instance.control.get('requests') as MicRequest[]) ?? []).slice())
    }

    instance.messages.observeDeep(readMessages)
    instance.sidechat.observe(readSide)
    instance.queue.observe(readQueue)
    instance.pins.observe(readPins)
    instance.control.observe(readControl)
    instance.provider.awareness.on('change', syncPeers)
    instance.provider.on('status', onStatus)

    readMessages()
    readSide()
    readQueue()
    readPins()
    readControl()
    syncPeers()

    return () => {
      instance.messages.unobserveDeep(readMessages)
      instance.sidechat.unobserve(readSide)
      instance.queue.unobserve(readQueue)
      instance.pins.unobserve(readPins)
      instance.control.unobserve(readControl)
      instance.provider.awareness.off('change', syncPeers)
      instance.provider.off('status', onStatus)
      instance.destroy()
      setSession(null)
    }
  }, [code, me.member_id, me.name, me.color])

  // --- control socket ---------------------------------------------------------

  useEffect(() => {
    const socket = new ControlSocket(code, me.member_id)
    controlRef.current = socket

    const unsubscribeFatal = socket.onFatal(setEnded)

    const unsubscribe = socket.on((event: ControlEvent) => {
      if (event.type === 'ready') {
        setModelLabel(`${event.provider ?? ''} · ${event.model ?? ''}`)
        return
      }

      if (event.scope === 'fork') {
        if (event.type === 'delta') {
          setForkTurns((turns) => {
            const next = [...turns]
            const index = next.findIndex((t) => t.streaming)
            if (index >= 0) next[index] = { ...next[index], content: next[index].content + (event.text ?? '') }
            return next
          })
        } else if (event.type === 'done') {
          setForkBusy(false)
          setForkTurns((turns) => turns.map((t) => ({ ...t, streaming: false })))
        } else if (event.type === 'error') {
          setForkBusy(false)
          setError(event.error ?? 'the private question failed')
        }
        return
      }

      if (event.type === 'error') {
        setError(event.error ?? 'something went wrong')
        window.setTimeout(() => setError(null), 4000)
      }
    })

    return () => {
      unsubscribe()
      unsubscribeFatal()
      socket.destroy()
      controlRef.current = null
    }
  }, [code, me.member_id])

  // --- derived ----------------------------------------------------------------

  const isDriver = driver === me.member_id
  const driverName = useMemo(() => {
    if (!driver) return null
    if (driver === me.member_id) return me.name
    return driverNameRaw || 'Someone'
  }, [driver, driverNameRaw, me.member_id, me.name])

  const streaming = messages.some((m) => m.role === 'assistant' && !m.done)
  const myRequestPending = requests.some((r) => r.id === me.member_id)

  // --- actions ----------------------------------------------------------------

  const send = useCallback((body: string) => {
    if (body.trim()) controlRef.current?.send({ type: 'send', body: body.trim() })
  }, [])

  const sendQueued = useCallback((id: string) => {
    controlRef.current?.send({ type: 'send_queued', id })
  }, [])

  const stop = useCallback(() => controlRef.current?.send({ type: 'stop' }), [])

  const chooseModel = useCallback((id: string, name: string) => {
    controlRef.current?.send({ type: 'set_model', model: id, name })
  }, [])
  const requestMic = useCallback(() => controlRef.current?.send({ type: 'request_mic' }), [])
  const withdrawRequest = useCallback(
    () => controlRef.current?.send({ type: 'withdraw_request' }),
    [],
  )
  const grantMic = useCallback(
    (member: string) => controlRef.current?.send({ type: 'grant_mic', member }),
    [],
  )
  const releaseMic = useCallback(() => controlRef.current?.send({ type: 'release_mic' }), [])

  const sayInSideChat = useCallback((body: string) => {
    if (body.trim()) controlRef.current?.send({ type: 'sidechat', body: body.trim() })
  }, [])

  const promote = useCallback((id: string) => controlRef.current?.send({ type: 'promote', id }), [])

  const addToQueue = useCallback((body: string) => {
    if (body.trim()) controlRef.current?.send({ type: 'queue', body: body.trim() })
  }, [])

  const dropFromQueue = useCallback(
    (id: string) => {
      if (!session) return
      const index = session.queue.toArray().findIndex((item) => item.id === id)
      if (index >= 0) session.queue.delete(index, 1)
    },
    [session],
  )

  const togglePin = useCallback(
    (messageId: string) => {
      if (!session) return
      if (session.pins.has(messageId)) session.pins.delete(messageId)
      else session.pins.set(messageId, { by: me.member_id, at: Date.now() / 1000 })
    },
    [session, me.member_id],
  )

  const toggleReaction = useCallback(
    (messageId: string, emoji: string) => {
      if (!session) return
      const entry = session.messages.toArray().find((m) => String(m.get('id')) === messageId)
      if (!entry) return
      const reactions = entry.get('reactions') as Y.Map<string[]>
      const holders = [...(reactions.get(emoji) ?? [])]
      const index = holders.indexOf(me.member_id)
      if (index >= 0) holders.splice(index, 1)
      else holders.push(me.member_id)
      if (holders.length) reactions.set(emoji, holders)
      else reactions.delete(emoji)
    },
    [session, me.member_id],
  )

  const askPrivately = useCallback(
    (body: string) => {
      const question = body.trim()
      if (!question) return
      setForkBusy(true)
      setForkTurns((turns) => [
        ...turns,
        { role: 'user', content: question },
        { role: 'assistant', content: '', streaming: true },
      ])
      controlRef.current?.send({
        type: 'fork',
        job: newJobId(),
        body: question,
        history: forkTurns.map((t) => ({ role: t.role, content: t.content })),
      })
    },
    [forkTurns],
  )

  /**
   * Publish a private exchange to the room.
   *
   * This shows everyone what was already said. It deliberately does not send
   * the answer as a new prompt: doing that made the assistant reply to its own
   * words, which is how this was originally broken.
   */
  const shareFork = useCallback((question: string, answer: string) => {
    if (answer.trim()) {
      controlRef.current?.send({ type: 'share_fork', question, answer })
    }
  }, [])

  return {
    session,
    connected,
    ended,
    peers,
    messages,
    sidechat,
    queue,
    pins,
    driver,
    driverName,
    isDriver,
    requests,
    myRequestPending,
    streaming,
    error,
    modelLabel,
    model,
    chooseModel,
    forkTurns,
    forkBusy,
    send,
    sendQueued,
    stop,
    requestMic,
    withdrawRequest,
    grantMic,
    releaseMic,
    sayInSideChat,
    promote,
    addToQueue,
    dropFromQueue,
    togglePin,
    toggleReaction,
    askPrivately,
    shareFork,
  }
}
