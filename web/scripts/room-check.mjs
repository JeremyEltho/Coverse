/**
 * Protocol level check of the room stack against a running server.
 *
 * Connects real y-websocket clients plus control sockets, with no browser, and
 * verifies the parts that are easy to get wrong: the baton, streaming into
 * shared state, side chat staying out of the model's context, and stop.
 *
 * Usage: node scripts/room-check.mjs [httpBase]
 */
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import WS from 'ws'

const http = process.argv[2] || 'http://127.0.0.1:8000'
const ws = http.replace('http', 'ws')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const results = []
const check = (label, ok, detail = '') => {
  results.push({ label, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` -- ${detail}` : ''}`)
}

async function api(path, body) {
  const res = await fetch(`${http}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

async function waitFor(predicate, label, timeoutMs = 15000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (predicate()) return true
    await sleep(80)
  }
  throw new Error(`timeout waiting for: ${label}`)
}

const { code } = await api('/api/rooms', {})

async function member(name) {
  const me = await api(`/api/rooms/${code}/join`, { name })
  const doc = new Y.Doc()
  const provider = new WebsocketProvider(`${ws}/ws/room`, code, doc, {
    WebSocketPolyfill: WS,
    params: { member: me.member_id },
    connect: true,
  })
  const control = new WS(`${ws}/ws/control/${code}?member=${me.member_id}`)
  const events = []
  control.on('message', (raw) => events.push(JSON.parse(raw.toString())))
  await new Promise((res, rej) => { control.on('open', res); control.on('error', rej) })
  return {
    me, doc, provider, control, events,
    send: (msg) => control.send(JSON.stringify(msg)),
    messages: () => doc.getArray('messages').toArray().map((m) => ({
      role: m.get('role'), author: m.get('author_name'),
      body: m.get('body').toString(), done: m.get('done'),
    })),
    control_: () => doc.getMap('control'),
  }
}

const alice = await member('Alice')
const bob = await member('Bob')
await waitFor(() => alice.provider.wsconnected && bob.provider.wsconnected, 'connected')
check('two members connect to one room', true, `code ${code}`)

// Alice joined first, so she holds the mic.
await waitFor(() => alice.control_().get('driver') === alice.me.member_id, 'alice drives')
check('first member automatically holds the mic', true)

// A spectator cannot send.
bob.send({ type: 'send', body: 'i should not be able to do this' })
await waitFor(() => bob.events.some((e) => e.type === 'error'), 'refusal')
check('spectator send is refused', bob.events.some((e) => /mic/.test(e.error ?? '')))

// The driver sends, and it streams into BOTH clients' shared state.
alice.send({ type: 'send', body: 'what should we build at this hackathon' })
await waitFor(() => bob.messages().some((m) => m.role === 'user'), 'bob sees the prompt')
check('prompt appears in every client', true)

await waitFor(() => bob.messages().some((m) => m.role === 'assistant' && m.body.length > 20),
  'bob sees the reply streaming')
check('AI reply streams into spectator state', true)

await waitFor(() => bob.messages().some((m) => m.role === 'assistant' && m.done), 'reply done')
const aliceThread = JSON.stringify(alice.messages())
const bobThread = JSON.stringify(bob.messages())
check('both clients converged on the thread', aliceThread === bobThread,
  `${alice.messages().length} messages`)

// Side chat is shared between humans but must never reach the model.
bob.send({ type: 'sidechat', body: 'SECRETBACKCHANNEL this idea is weak' })
await waitFor(() => alice.doc.getArray('sidechat').length > 0, 'alice sees side chat')
check('side chat reaches other humans', true)
check('side chat stays out of the AI thread',
  !alice.messages().some((m) => m.body.includes('SECRETBACKCHANNEL')))

// The queue belongs to the room: a spectator contributes without the mic.
bob.send({ type: 'queue', body: 'ask it about offline mode' })
await waitFor(() => alice.doc.getArray('queue').length === 1, 'queued')
check('spectator can add to the shared queue', true)

// Mic request and grant.
bob.send({ type: 'request_mic' })
await waitFor(() => (alice.control_().get('requests') ?? []).length === 1, 'request visible')
check('mic request is visible to the driver', true)

// The shared draft must survive the handoff.
alice.doc.getText('composer').insert(0, 'half typed thought')
await waitFor(() => bob.doc.getText('composer').toString().includes('half typed'), 'draft shared')
check('composer draft is shared live', true)

alice.send({ type: 'grant_mic', member: bob.me.member_id })
await waitFor(() => bob.control_().get('driver') === bob.me.member_id, 'bob drives')
check('granting the mic moves the baton', true)
check('pending request cleared on grant', (bob.control_().get('requests') ?? []).length === 0)
check('draft survives the handoff',
  bob.doc.getText('composer').toString() === 'half typed thought')

// Bob now drives; Alice cannot send but can still stop.
alice.events.length = 0
alice.send({ type: 'send', body: 'nope' })
await waitFor(() => alice.events.some((e) => e.type === 'error'), 'alice refused')
check('the previous driver loses send rights', true)

bob.send({ type: 'send', body: 'write me something long please' })
await waitFor(() => bob.messages().filter((m) => m.role === 'assistant').length === 2, 'second reply')
await sleep(120)
alice.send({ type: 'stop' })
await waitFor(() => {
  const last = bob.messages().filter((m) => m.role === 'assistant').pop()
  return last && last.done
}, 'reply stopped')
const stoppedAt = bob.messages().filter((m) => m.role === 'assistant').pop().body.length
await sleep(700)
const stillAt = bob.messages().filter((m) => m.role === 'assistant').pop().body.length
check('any member can stop a running reply', stoppedAt === stillAt,
  `froze at ${stoppedAt} chars`)

// A private fork answers only its asker and leaves the room untouched.
const threadBefore = alice.messages().length
alice.events.length = 0
alice.send({ type: 'fork', job: 'f1', body: 'quietly explain that last answer' })
await waitFor(() => alice.events.some((e) => e.type === 'done' && e.scope === 'fork'),
  'fork answered')
check('private fork returns an answer to its asker',
  (alice.events.find((e) => e.type === 'done' && e.scope === 'fork').answer ?? '').length > 0)
await sleep(300)
check('private fork does not touch the shared thread',
  alice.messages().length === threadBefore && bob.messages().length === threadBefore)

// Promoting is a driver action, since it costs a turn.
alice.events.length = 0
const sideId = alice.doc.getArray('sidechat').get(0).id
alice.send({ type: 'promote', id: sideId })
await waitFor(() => alice.events.some((e) => e.type === 'error'), 'promote refused')
check('promoting requires the mic', true)

alice.provider.destroy(); alice.control.close()
bob.provider.destroy(); bob.control.close()

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
