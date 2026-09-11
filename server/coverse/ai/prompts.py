"""Prompt construction for a room with several people in it.

The model is talking to a group, not a person. Two things follow:

* Every turn is labelled with who said it, so the model can tell that two people
  are disagreeing, build on what a specific person suggested, and address people
  by name. A merged single voice would flatten exactly the part of a group
  conversation that is interesting.
* The side chat is never included. It is the backchannel where people say "this
  is a dead end, ask it about X instead", and it only reaches the model when
  somebody deliberately promotes a line into the thread.
"""

from __future__ import annotations

from .base import Message

SYSTEM = """You are an assistant in a shared room with several people in it.
Messages are labelled with who wrote them. Different people may want different
things; when they disagree, address the disagreement rather than silently
picking a side. Refer to people by name when it helps. Reply to the most recent
message, taking the earlier conversation into account.

Answer normally and directly. Do not narrate the fact that you are in a group."""

FORK_NOTE = """This is a private side question from one person in the room. The
conversation above is the room's shared thread, for context. Your answer is shown
only to the person asking unless they choose to share it."""

# Keep the labelled transcript bounded. Rooms are short lived, so this is a
# safety valve rather than something a normal session will hit.
MAX_TURNS = 60


def _label(turn: dict[str, str]) -> Message:
    """One transcript turn as a provider message.

    Human turns become user messages prefixed with the speaker's name. The
    model's own turns stay unlabelled assistant messages, which is what the
    chat APIs expect.
    """
    if turn["role"] == "assistant":
        return Message("assistant", turn["body"])
    name = turn.get("author_name") or "Someone"
    return Message("user", f"{name}: {turn['body']}")


def build(transcript: list[dict[str, str]], *, fork: bool = False) -> list[Message]:
    """Turn a room transcript into provider messages."""
    system = SYSTEM if not fork else f"{SYSTEM}\n\n{FORK_NOTE}"
    messages: list[Message] = [Message("system", system)]

    for turn in transcript[-MAX_TURNS:]:
        if not turn.get("body", "").strip():
            continue  # skip the empty assistant placeholder being streamed into
        messages.append(_label(turn))

    return messages


def roster_line(names: list[str]) -> str:
    """A system note naming who is currently in the room."""
    if not names:
        return "The room is empty."
    if len(names) == 1:
        return f"{names[0]} is in the room."
    return f"In the room: {', '.join(names[:-1])} and {names[-1]}."
