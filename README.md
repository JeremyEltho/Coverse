# Coverse

A chatbot the whole room can use at once.

One assistant, several people. Whoever holds the mic talks to it; everyone else
watches the reply arrive on their own screen, argues in a side chat the model
never sees, stacks up prompts for the driver, edits the draft as it is being
typed, and can quietly ask their own question without interrupting anyone.

It exists because of a specific moment: four people crowded around one laptop at
a hackathon, shouting suggestions at whoever is typing. That works brilliantly
until you are not at the same table.

## Running it

Nothing is required beyond Python and Node. The default AI provider is a mock
that fake-streams realistic output, so the whole product works with no API keys
and nothing installed.

```bash
make setup     # install backend and frontend dependencies
make dev       # backend on :8000, frontend on :5173
```

Open http://localhost:5173, start a room, and share the link or read out the six
character code. To see it properly, open the same room in a second browser under
a different name and watch a reply land in both at once.

## Using a real model

One environment variable switches backends. Copy `.env.example` to `.env` first.

```bash
# a local model through Ollama
AI_PROVIDER=ollama
OLLAMA_MODEL=llama3.2        # ollama pull llama3.2

# or hosted models through OpenRouter
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
```

`GET /health` reports whether the provider is actually reachable and says what to
do when it is not: daemon down, model never pulled, key missing.

## How it works

### The mic

An assistant that answers every message is unusable in a group chat, because
most messages are people talking to each other. Rather than guessing whether it
was addressed, one person holds the mic and only they can send. Everything else
follows from that: turn taking is solved socially, so the model can stay simple
and reply to everything it receives.

Spectators are not passive. They can type into the shared draft, queue prompts,
react, pin, ask for the mic, and ask their own private question.

| Action | Who |
| --- | --- |
| Send to the assistant | driver only |
| Stop a running reply | anyone, because a bad answer wastes everyone's time |
| Edit the shared draft | anyone |
| Add to the prompt queue | anyone |
| Promote a side chat line into the thread | driver, since it costs a turn |
| Ask privately | anyone |

### Everything shared is one Yjs document

The thread, the side chat, the queue, the draft, the pins and the baton all live
in a single CRDT document synced over one websocket. There is no fan-out code
and no polling, which has two consequences worth knowing:

- **Streaming is free.** A reply's body is a `Y.Text`, and the server writes
  tokens into it on its own replica. Every member watches it fill in, and
  somebody joining halfway through syncs into the middle of a half written reply
  correctly.
- **The shared composer is free.** It is a `Y.Text` with cursors. Local edits are
  diffed to a single changed span and remote edits map the caret, so it stays on
  the same words instead of jumping to the end when someone else types.

A second websocket carries commands only: send, stop, pass the mic, promote,
fork. AI output never travels on it.

### Rooms are ephemeral

No accounts, no database, nothing on disk. You pick a name, optionally a room
password, and the room exists only while people are in it. Two graces stop that
from being hostile: an empty room survives a couple of minutes so a refresh does
not destroy the session, and a disconnected driver keeps the mic briefly so one
closed laptop cannot block everyone.

Nothing is stored, so the takeaway is an export. Pins and the full transcript
come out as markdown, built in the browser.

## Layout

```
server/                     FastAPI, Python 3.11+
  coverse/crdt/room.py      the shared room document
  coverse/ai/               provider abstraction and the two actions
  coverse/ws/               room registry, sync socket, control socket
  coverse/api/              create and join rooms
web/
  src/lib/                  Yjs connection, control socket, origin resolution
  src/hooks/                the room session, and the shared textarea binding
  src/room/                 thread, composer, mic bar, rail
```

## Testing

```bash
make test    # 41 backend tests, plus the frontend typecheck
make lint    # ruff and mypy
make check   # protocol and browser checks, needs `make dev` running
```

`room-check.mjs` drives the protocol with raw clients and no browser.
`e2e-check.mjs` puts four people in one room in real browsers, because most of
what can break here only breaks with an audience: a reply reaching every screen,
a draft surviving a handoff, side chat staying out of the model's context, and
any spectator pulling the brake.

## Deployment

The backend is a container (`server/Dockerfile`, `server/railway.toml`) and the
frontend is a static bundle (`web/vercel.json`). Build the frontend with
`VITE_BACKEND_ORIGIN` set to the backend's public origin, since a deployed bundle
has no dev proxy and a websocket needs an absolute URL.

The backend must run as a single replica. A room is one live Yjs replica in
process memory; a second instance would put half the room in a different copy
with no way to reconcile.
