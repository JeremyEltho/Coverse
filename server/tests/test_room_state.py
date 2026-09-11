"""The shared room document: the thread, the mic, the queue and the draft."""

from __future__ import annotations

from coverse.crdt.room import RoomDoc


def test_a_reply_body_is_a_live_text_that_can_be_streamed_into():
    """The body has to be a Text, not a string, or spectators see nothing until
    the reply is finished."""
    room = RoomDoc()
    _, entry = room.add_message(role="assistant", author="ai", author_name="Assistant")
    body = room.message_body(entry)

    for chunk in ["Partial", " answer", " arriving."]:
        body.insert(len(str(body)), chunk)

    assert room.transcript()[-1]["body"] == "Partial answer arriving."
    assert entry["done"] is False
    room.finish_message(entry)
    assert entry["done"] is True


def test_transcript_keeps_speakers_apart():
    room = RoomDoc()
    room.add_message(role="user", author="u1", author_name="Alice", body="one")
    room.add_message(role="user", author="u2", author_name="Bob", body="two")

    assert [(t["author_name"], t["body"]) for t in room.transcript()] == [
        ("Alice", "one"),
        ("Bob", "two"),
    ]


def test_granting_the_mic_clears_that_persons_request():
    room = RoomDoc()
    room.set_driver("u1", "Alice")
    room.request_mic("u2", "Bob")
    assert len(room.control.get("requests")) == 1

    room.set_driver("u2", "Bob")
    assert room.driver == "u2"
    assert room.driver_name == "Bob"
    assert room.control.get("requests") == []


def test_requesting_the_mic_twice_does_not_duplicate():
    room = RoomDoc()
    room.request_mic("u2", "Bob")
    room.request_mic("u2", "Bob")
    assert len(room.control.get("requests")) == 1

    room.withdraw_request("u2")
    assert room.control.get("requests") == []


def test_queue_items_survive_being_taken_exactly_once():
    room = RoomDoc()
    item_id = room.add_to_queue(author="u3", author_name="Cy", body="ask about pricing")

    taken = room.take_from_queue(item_id)
    assert taken is not None and taken["body"] == "ask about pricing"
    assert len(room.queue) == 0
    assert room.take_from_queue(item_id) is None


def test_pins_and_reactions_toggle():
    room = RoomDoc()
    message_id, entry = room.add_message(
        role="assistant", author="ai", author_name="Assistant", body="useful"
    )

    assert room.toggle_pin(message_id, "u1") is True
    assert room.toggle_pin(message_id, "u1") is False

    room.toggle_reaction(message_id, "🔥", "u1")
    room.toggle_reaction(message_id, "🔥", "u2")
    assert sorted(entry["reactions"]["🔥"]) == ["u1", "u2"]

    room.toggle_reaction(message_id, "🔥", "u1")
    assert list(entry["reactions"]["🔥"]) == ["u2"]

    room.toggle_reaction(message_id, "🔥", "u2")
    assert "🔥" not in entry["reactions"]


def test_side_chat_is_separate_from_the_thread():
    room = RoomDoc()
    room.add_sidechat(author="u1", author_name="Alice", body="this is a dead end")
    assert len(room.sidechat) == 1
    assert room.transcript() == []


def test_the_shared_draft_clears_and_returns_what_it_held():
    room = RoomDoc()
    room.set_composer("half a thought")
    assert str(room.composer) == "half a thought"
    assert room.clear_composer() == "half a thought"
    assert str(room.composer) == ""


def test_two_replicas_of_a_room_converge():
    a = RoomDoc()
    a.add_message(role="user", author="u1", author_name="Alice", body="from A")

    b = RoomDoc()
    b.apply_update(a.encode_update())
    b.add_message(role="user", author="u2", author_name="Bob", body="from B")
    a.apply_update(b.encode_update())

    assert a.transcript() == b.transcript()
    assert len(a.transcript()) == 2


def test_a_shared_message_is_marked_as_such():
    """Sharing a private exchange must not look like it was asked out loud."""
    room = RoomDoc()
    room.add_message(
        role="user", author="u1", author_name="Panda", body="what are they on about", shared=True
    )
    _, answer = room.add_message(
        role="assistant",
        author="assistant",
        author_name="Assistant",
        body="They are discussing X.",
        shared=True,
        done=True,
    )

    assert all(entry["shared"] for entry in room.messages)
    assert answer["done"] is True, "a shared answer is already complete, not streaming"


def test_an_ordinary_message_is_not_marked_shared():
    room = RoomDoc()
    _, entry = room.add_message(role="user", author="u1", author_name="Alice", body="hi")
    assert entry["shared"] is False


def test_the_chosen_model_is_shared_room_state():
    """One conversation means one model, and everyone should see which."""
    room = RoomDoc()
    room.set_model("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B")
    assert room.model == "meta-llama/llama-3.3-70b-instruct"
    assert room.model_name == "Llama 3.3 70B"

    other = RoomDoc()
    other.apply_update(room.encode_update())
    assert other.model_name == "Llama 3.3 70B"
