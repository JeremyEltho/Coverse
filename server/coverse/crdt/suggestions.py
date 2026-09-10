"""Pending AI suggestions, stored inside the document itself.

Suggestions live in a shared ``Y.Map`` on the same Doc as the text, which means
they are collaborative for free: everyone connected sees a pending rewrite appear,
and anyone can accept or reject it. It also means they survive a server restart
along with the rest of the document.

A suggestion is a plain JSON-serializable dict so both Python and the browser can
read it without a schema layer:

    {
      "id":        "sug_...",
      "kind":      "rewrite" | "comment",
      "status":    "pending" | "accepted" | "rejected",
      "original":  "the text the user selected",
      "replacement": "what the model proposes",   # rewrite only
      "body":      "the model's remark",          # comment only
      "relpos":    {"from": "<base64>", "to": "<base64>"},  # y-tiptap relative positions
      "anchor":    {"text": ..., "offset": ...},  # server-side fallback anchor
      "author":    "user id that requested it",
      "created_at": 1699999999.0
    }
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pycrdt import Map

SuggestionKind = Literal["rewrite", "comment"]
SuggestionStatus = Literal["pending", "accepted", "rejected"]


def new_id() -> str:
    return f"sug_{uuid.uuid4().hex[:12]}"


def create(
    suggestions: Map,
    *,
    kind: SuggestionKind,
    original: str,
    author: str,
    replacement: str | None = None,
    body: str | None = None,
    relpos: dict[str, str] | None = None,
    anchor: dict[str, Any] | None = None,
    suggestion_id: str | None = None,
) -> str:
    """Write a pending suggestion into the doc and return its id."""
    suggestion_id = suggestion_id or new_id()
    record: dict[str, Any] = {
        "id": suggestion_id,
        "kind": kind,
        "status": "pending",
        "original": original,
        "author": author,
        "created_at": time.time(),
    }
    if replacement is not None:
        record["replacement"] = replacement
    if body is not None:
        record["body"] = body
    if relpos:
        record["relpos"] = relpos
    if anchor:
        record["anchor"] = anchor

    doc = suggestions.doc
    if doc is None:
        suggestions[suggestion_id] = record
    else:
        with doc.transaction():
            suggestions[suggestion_id] = record
    return suggestion_id


def update(suggestions: Map, suggestion_id: str, **changes: Any) -> dict[str, Any] | None:
    """Merge ``changes`` into an existing suggestion, returning the new record."""
    existing = get(suggestions, suggestion_id)
    if existing is None:
        return None
    merged = {**existing, **changes}
    doc = suggestions.doc
    if doc is None:
        suggestions[suggestion_id] = merged
    else:
        with doc.transaction():
            suggestions[suggestion_id] = merged
    return merged


def get(suggestions: Map, suggestion_id: str) -> dict[str, Any] | None:
    try:
        record = suggestions[suggestion_id]
    except KeyError:
        return None
    return dict(record) if record is not None else None


def remove(suggestions: Map, suggestion_id: str) -> None:
    doc = suggestions.doc
    try:
        if doc is None:
            del suggestions[suggestion_id]
        else:
            with doc.transaction():
                del suggestions[suggestion_id]
    except KeyError:
        pass


def list_pending(suggestions: Map) -> list[dict[str, Any]]:
    out = [dict(v) for v in suggestions.values() if v and dict(v).get("status") == "pending"]
    return sorted(out, key=lambda r: r.get("created_at", 0))


def prune(suggestions: Map, max_age_seconds: float = 60 * 60 * 24) -> int:
    """Drop resolved or stale suggestions. Returns how many were removed."""
    cutoff = time.time() - max_age_seconds
    doomed = [
        key
        for key, value in suggestions.items()
        if value
        and (dict(value).get("status") != "pending" or dict(value).get("created_at", 0) < cutoff)
    ]
    for key in doomed:
        remove(suggestions, key)
    return len(doomed)
