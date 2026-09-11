"""What the model is told, and what happens to what it says."""

from __future__ import annotations

from coverse.ai import actions, prompts
from coverse.ai.base import Delta, Message, Provider
from coverse.crdt.room import RoomDoc


class ScriptedProvider(Provider):
    name = "scripted"

    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls: list[list[Message]] = []

    async def stream(self, messages, **opts):
        self.calls.append(messages)
        for chunk in self.chunks:
            yield Delta(text=chunk)
        yield Delta(done=True)


def test_every_human_turn_is_labelled_with_its_speaker():
    transcript = [
        {"role": "user", "author_name": "Alice", "body": "one"},
        {"role": "assistant", "author_name": "Assistant", "body": "two"},
        {"role": "user", "author_name": "Bob", "body": "three"},
    ]
    built = prompts.build(transcript)

    assert built[0].role == "system"
    assert built[1].content == "Alice: one"
    # The model's own turns stay unlabelled, which is what the APIs expect.
    assert built[2].role == "assistant" and built[2].content == "two"
    assert built[3].content == "Bob: three"


def test_an_empty_streaming_placeholder_is_not_sent_to_the_model():
    transcript = [
        {"role": "user", "author_name": "Alice", "body": "hello"},
        {"role": "assistant", "author_name": "Assistant", "body": ""},
    ]
    assert len(prompts.build(transcript)) == 2


async def test_reply_streams_into_the_shared_thread():
    room = RoomDoc()
    room.add_message(role="user", author="u1", author_name="Alice", body="what next")
    provider = ScriptedProvider(["First part. ", "Second part."])

    events = await actions.collect(actions.reply(provider=provider, room=room, flush_ms=0))

    assert events[0]["type"] == "status"
    assert events[-1]["type"] == "done"
    last = room.transcript()[-1]
    assert last["role"] == "assistant"
    assert last["body"] == "First part. Second part."


async def test_the_side_chat_never_reaches_the_model():
    """The backchannel is the whole reason people can be honest in the room."""
    room = RoomDoc()
    room.add_message(role="user", author="u1", author_name="Alice", body="what next")
    room.add_sidechat(author="u2", author_name="Bob", body="SECRET this is weak")

    provider = ScriptedProvider(["ok"])
    await actions.collect(actions.reply(provider=provider, room=room, flush_ms=0))

    everything = " ".join(m.content for m in provider.calls[0])
    assert "SECRET" not in everything


async def test_the_roster_is_offered_to_the_model():
    room = RoomDoc()
    room.add_message(role="user", author="u1", author_name="Alice", body="hi")
    provider = ScriptedProvider(["ok"])

    await actions.collect(
        actions.reply(provider=provider, room=room, flush_ms=0, roster=["Alice", "Bob"])
    )

    assert any("Alice" in m.content and "Bob" in m.content for m in provider.calls[0])


async def test_a_fork_sees_the_room_but_changes_nothing_in_it():
    room = RoomDoc()
    room.add_message(role="user", author="u1", author_name="Alice", body="shared context")
    before = len(room.transcript())

    provider = ScriptedProvider(["a private answer"])
    events = await actions.collect(
        actions.fork_reply(provider=provider, room=room, question="just for me", asker_name="Cy")
    )

    assert events[-1]["answer"] == "a private answer"
    assert len(room.transcript()) == before, "a fork must not touch shared state"
    sent = " ".join(m.content for m in provider.calls[0])
    assert "shared context" in sent
    assert "Cy: just for me" in sent


async def test_delta_batcher_flushes_on_sentence_boundaries():
    batcher = actions.DeltaBatcher(flush_ms=10_000)  # the timer will not fire
    assert batcher.add("Hello") is None
    assert batcher.add(" world") is None
    assert batcher.add(". ") == "Hello world. "
