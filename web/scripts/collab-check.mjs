/**
 * End-to-end check of the collaboration stack against a running server.
 *
 * Connects two real y-websocket clients (the same library the browser uses) to
 * the Python sync socket, verifies that edits converge between them, then asks
 * the AI to write into the document over the chat socket and verifies that the
 * result reaches BOTH clients through CRDT sync.
 *
 * Usage: node scripts/collab-check.mjs [baseUrl] [docId]
 */
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import WS from 'ws'

const base = process.argv[2] || 'ws://127.0.0.1:8111'
const docId = process.argv[3] || `itest-${Date.now()}`
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function connect(name) {
  const doc = new Y.Doc()
  const provider = new WebsocketProvider(`${base}/ws/doc`, docId, doc, {
    WebSocketPolyfill: WS,
    params: { token: `user-${name}` },
    connect: true,
  })
  return { name, doc, provider, frag: doc.getXmlFragment('default') }
}

function insertParagraph(client, text) {
  const doc = client.doc
  doc.transact(() => {
    const p = new Y.XmlElement('paragraph')
    p.insert(0, [new Y.XmlText(text)])
    client.frag.push([p])
  })
}

async function waitFor(predicate, label, timeoutMs = 8000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (predicate()) return true
    await sleep(100)
  }
  throw new Error(`timeout waiting for: ${label}`)
}

const results = []
const check = (label, ok, detail = '') => {
  results.push({ label, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ` -- ${detail}` : ''}`)
}

const alice = connect('alice')
const bob = connect('bob')

await waitFor(() => alice.provider.wsconnected && bob.provider.wsconnected, 'both connected')
check('two clients connect to the Python sync socket', true)

// 1. Alice's edit reaches Bob.
insertParagraph(alice, 'Alice wrote this.')
await waitFor(() => bob.frag.toString().includes('Alice wrote this.'), 'bob sees alice')
check('edit propagates alice -> bob', true)

// 2. Bob's edit reaches Alice.
insertParagraph(bob, 'Bob wrote this.')
await waitFor(() => alice.frag.toString().includes('Bob wrote this.'), 'alice sees bob')
check('edit propagates bob -> alice', true)

// 3. Simultaneous edits converge rather than clobbering.
insertParagraph(alice, 'Simultaneous A')
insertParagraph(bob, 'Simultaneous B')
await waitFor(
  () =>
    alice.frag.toString().includes('Simultaneous B') &&
    bob.frag.toString().includes('Simultaneous A'),
  'convergence',
)
check(
  'concurrent edits converge identically',
  alice.frag.toString() === bob.frag.toString(),
  `${alice.frag.length} nodes`,
)

// 4. The AI writes into the document over the chat socket; both clients see it.
const chat = new WS(`${base.replace('ws://', 'ws://')}/ws/chat/${docId}?token=user-alice`)
const events = []
let aiPresenceSeen = false
alice.provider.awareness.on('change', () => {
  for (const state of alice.provider.awareness.getStates().values()) {
    if (state?.user?.isAI) aiPresenceSeen = true
  }
})

await new Promise((resolve, reject) => {
  chat.on('open', resolve)
  chat.on('error', reject)
})
chat.on('message', (raw) => events.push(JSON.parse(raw.toString())))

const before = alice.frag.toString()
chat.send(JSON.stringify({ type: 'generate', job: 'j1', prompt: 'write about CRDTs' }))

await waitFor(() => events.some((e) => e.type === 'done'), 'ai generation finished', 20000)
check('AI generate streams deltas over the chat socket', events.filter((e) => e.type === 'delta').length > 0,
  `${events.filter((e) => e.type === 'delta').length} deltas`)

await waitFor(() => alice.frag.toString() !== before, 'alice sees AI text')
await waitFor(() => bob.frag.toString() === alice.frag.toString(), 'bob converges on AI text')
check('AI edit reaches BOTH clients via CRDT sync', true, `${alice.frag.length} nodes`)
check('AI edit produced real structure, not literal markdown',
  !alice.frag.toString().includes('<paragraph>##'),
  alice.frag.toString().slice(0, 60))
check('AI presence broadcast to human clients', aiPresenceSeen)

// 5. Cancellation stops a job mid-flight.
const before2 = alice.frag.toString()
chat.send(JSON.stringify({ type: 'generate', job: 'j2', prompt: 'a very long document please' }))
await sleep(120)
chat.send(JSON.stringify({ type: 'cancel', job: 'j2' }))
await waitFor(() => events.some((e) => e.type === 'cancelled' && e.job === 'j2'), 'cancel ack', 10000)
const afterCancel = alice.frag.toString()
await sleep(600)
check('cancellation stops the stream and leaves the doc stable',
  afterCancel === alice.frag.toString(), 'no writes after cancel')

// 6. Rewrite arrives as a suggestion without touching the body.
const bodyBefore = alice.frag.toString()
chat.send(JSON.stringify({ type: 'rewrite', job: 'j3', selection: 'Alice wrote this.', instruction: 'punchier' }))
await waitFor(() => events.some((e) => e.type === 'suggestion' && e.job === 'j3'), 'suggestion', 10000)
await sleep(300)
check('rewrite creates a suggestion and does NOT edit the body',
  alice.frag.toString() === bodyBefore)

const sugMap = alice.doc.getMap('suggestions')
check('suggestion is visible in the shared CRDT map', sugMap.size > 0, `${sugMap.size} entries`)

chat.close()
alice.provider.destroy()
bob.provider.destroy()

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
