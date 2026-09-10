"""Tracking a region of the document across concurrent edits.

Three different problems, three different answers -- this module exists mostly to
write the reasoning down, because getting it wrong produces corruption that only
shows up under real concurrency.

**Streaming generation.** The AI creates its own block and keeps the live
``XmlElement`` handle. pycrdt handles stay valid when other clients insert or
delete siblings around them, so appending at ``len(text)`` is always correct with
no index arithmetic. Verified in ``tests/test_crdt_document.py``.

**Selection rewrites and comments.** These anchor to a range of *existing* text
that a human may edit while the model is thinking. pycrdt's ``StickyIndex`` does
not support ``XmlText`` (only flat sequences), so the anchor is created on the
client with y-tiptap's ``absolutePositionToRelativePosition``, travels through
the server as an opaque base64 blob, and is resolved back to an absolute position
on the client at accept time. The server never interprets it -- it only needs the
plain selected text, which it gets as a string for the prompt.

**Server-side re-resolution.** When the server does need to locate previously
seen text (recovery, tests, applying a rewrite with no client present), it
re-finds it by content near the last known offset. ``resolve_text_anchor`` below
does that; it is a heuristic fallback, not the primary path.
"""

from __future__ import annotations

from dataclasses import dataclass

from pycrdt import XmlText


@dataclass(frozen=True)
class TextAnchor:
    """A best-effort, content-addressed pointer into a text node."""

    text: str
    offset: int

    def to_json(self) -> dict[str, object]:
        return {"text": self.text, "offset": self.offset}

    @classmethod
    def from_json(cls, data: dict) -> TextAnchor:
        return cls(text=str(data.get("text", "")), offset=int(data.get("offset", 0)))


def resolve_text_anchor(node: XmlText, anchor: TextAnchor) -> tuple[int, int] | None:
    """Locate ``anchor.text`` inside ``node``, preferring the closest match.

    Returns a ``(start, end)`` range, or ``None`` if the text is gone -- in which
    case the caller must drop the suggestion rather than guess, since applying a
    rewrite to the wrong range is worse than not applying it.
    """
    if not anchor.text:
        return None

    haystack = str(node)

    # Fast path: still exactly where we left it.
    if haystack[anchor.offset : anchor.offset + len(anchor.text)] == anchor.text:
        return anchor.offset, anchor.offset + len(anchor.text)

    # Otherwise take the occurrence nearest the remembered offset, so repeated
    # phrases resolve to the one the user actually selected.
    best: int | None = None
    start = haystack.find(anchor.text)
    while start != -1:
        if best is None or abs(start - anchor.offset) < abs(best - anchor.offset):
            best = start
        start = haystack.find(anchor.text, start + 1)

    if best is None:
        return None
    return best, best + len(anchor.text)


def replace_range(node: XmlText, start: int, end: int, replacement: str) -> None:
    """Replace ``[start, end)`` in a text node as one atomic transaction."""
    doc = node.doc
    if doc is None:
        raise ValueError("text node is not integrated into a document")
    with doc.transaction():
        if end > start:
            del node[start:end]
        if replacement:
            node.insert(start, replacement)
