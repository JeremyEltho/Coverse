# Coverse

A collaborative document editor with an AI in the room.

Two modes over one shared document:

- **Document mode** — a Google-Docs-style editor. Multiple people, multi-cursor, presence. The assistant is another participant: ask it to write and its text streams into the document live for everyone; select a passage and ask for a rewrite or a review and it comes back as a suggestion you accept or reject.
- **Canvas mode** — conversation on the left, the document it produces on the right. You talk, the assistant builds and revises the document, and you can still edit it by hand at any time.

The backend is a real Yjs peer, not a relay. It holds a live CRDT replica of every open document, so AI edits are ordinary CRDT transactions that merge correctly against whatever humans are typing at the same moment.

## Running it

Nothing is required beyond Python and Node. The default AI provider is a mock that fake-streams realistic output, so the whole product works with no API keys and nothing installed.

```bash
make setup     # install backend and frontend dependencies
make dev       # backend on :8000, frontend on :5173
```

Open http://localhost:5173, pick a display name, and create a document. To see collaboration, open the same document URL in a second browser (or a private window) under a different name.

## Using a real model

Everything is driven by one environment variable. Copy `.env.example` to `.env` first.

```bash
# a local model through Ollama
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2        # ollama pull llama3.2

# or hosted models through OpenRouter
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
```

`GET /health` reports whether the provider is actually reachable, and says what to do when it is not (daemon down, model not pulled, key missing).

## Architecture

```
server/                     FastAPI, Python 3.11+
  coverse/crdt/             the CRDT layer: document model, AI edit primitives,
                            position anchoring, suggestion store
  coverse/ai/               provider abstraction (mock / ollama / openrouter)
                            and the actions that turn output into edits
  coverse/ws/               rooms, the Yjs sync socket, the chat socket
  coverse/db/               SQLAlchemy models and queries
  coverse/api/              REST endpoints
web/                        Vite + React + TypeScript
  src/editor/               TipTap editor, suggestion decorations, relative positions
  src/modes/                the two layouts over one shared session
  src/hooks/                the session hook both modes are built on
supabase/migrations/        Postgres schema and row level security
```

### Two sockets

| Socket | Carries |
| --- | --- |
| `/ws/doc/{id}` | Binary Yjs sync and awareness. Stock `y-websocket` clients talk to it unmodified. |
| `/ws/chat/{id}` | JSON: chat turns, AI action requests, streamed tokens, job status. |

The split is deliberate. Document mutations belong to the CRDT; conversation and control do not. An AI edit requested over the chat socket still reaches every client through the sync socket, which is why everyone sees the assistant write, not just the person who asked.

### What the AI can do

| Action | Trigger | Behaviour |
| --- | --- | --- |
| Generate | assistant panel | Writes into the document directly, streaming, with its own cursor. |
| Rewrite | select text → Rewrite | A suggestion. The body is untouched until someone accepts. |
| Review | select text → Review | A margin comment. Never edits. |
| Ask | assistant panel | Answers from the document as context. Never edits. |
| Canvas | canvas mode | Rebuilds the whole document from the conversation. |

Direct edits for generation, reviewable suggestions for anything that changes words you already wrote.

### Design notes

A few decisions that are load-bearing, and the reasons behind them:

- **The server writes ProseMirror nodes, not text.** The shared type is an `XmlFragment` whose structure must match the TipTap schema exactly, including attribute *types* — a heading level written as the string `"2"` instead of the number `2` corrupts the document in the browser. `scripts/crdt-roundtrip.mjs` verifies Python-authored updates against the real schema.
- **Streaming gains structure per block.** Text arrives as a plain paragraph so it appears instantly, then each completed block is re-parsed and swapped for the right node, so `## Heading` becomes a real heading instead of literal characters.
- **Token batching.** One CRDT transaction per token is a write storm, so deltas are committed on a short timer or at sentence boundaries.
- **Suggestions anchor to Yjs relative positions**, created and resolved on the client. A selection made before the model answers still points at the right words afterwards, even if someone edited above it. If the anchored text is deleted, the suggestion is marked stale rather than applied somewhere wrong.
- **Cancelling leaves committed text in place**, which is what interrupting a collaborator mid-sentence actually looks like.
- **Link sharing is on by default** (`link_access`), the way a collaborative editor is expected to work. Owners can restrict a document; read access never implies the right to delete.

## Auth and persistence

Without Supabase configured, the app runs in dev mode: you pick a display name, the backend trusts it, and documents live in SQLite. Set `AUTH_REQUIRED=true` in production so that mode can never be reached.

With Supabase, apply `supabase/migrations/0001_init.sql`, then set:

```bash
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_JWT_SECRET=<jwt secret>            # or leave blank to verify via JWKS
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@<host>:6543/postgres
AUTH_REQUIRED=true
```

Both JWT styles are supported: the classic shared secret (HS256) and asymmetric signing keys via JWKS. Tokens reach the websockets as a query parameter, since browsers cannot set headers on a WebSocket handshake.

Yjs updates are stored as an append-only log and compacted once a document accumulates enough of them, so concurrent writers never overwrite each other and a document can always be rebuilt by replaying it.

## Testing

```bash
make test    # 36 backend tests, plus a frontend typecheck
make lint    # ruff and mypy
make e2e     # drives the real app in a browser with two users
```

The end-to-end check signs in two users, opens one document in both, and asserts that edits propagate both ways, that concurrent edits converge, that AI writing reaches both clients, that a rewrite creates a suggestion without touching the body, and that accepting it propagates. `scripts/collab-check.mjs` does the same at the protocol level with raw `y-websocket` clients and no browser.
