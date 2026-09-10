"""The TipTap/ProseMirror schema contract, as seen from Python.

The browser editor and this module must agree exactly on how ProseMirror nodes
are represented inside the shared `XmlFragment`, because both sides write to it.
The rules, verified against `@tiptap/y-tiptap` by `scripts/crdt-roundtrip.mjs`:

* A ProseMirror node is an `XmlElement` whose tag is the node's *camelCase* type
  name (`bulletList`, not `bulletlist` -- `XmlFragment.__str__` lowercases tags
  for display, but the stored tag keeps its case).
* Text is an `XmlText`. Marks are applied as formatting attributes on the text
  range, using the mark's type name as the key.
* Node attributes are stored with their native type. Integers must be written as
  Python ``int`` (not ``str``): pycrdt encodes those as Yjs numbers, which is what
  the browser produces and expects. Writing ``"2"`` yields the string ``"2"`` on
  the other side and silently corrupts things like heading levels.
* Attributes whose value is ``None`` are omitted entirely, matching the browser.
"""

from __future__ import annotations

from typing import Any

# Nodes the v1 editor ships with (TipTap StarterKit subset). Frozen here because
# the AI edit helpers below encode it.
BLOCK_NODES = frozenset(
    {
        "paragraph",
        "heading",
        "blockquote",
        "codeBlock",
        "bulletList",
        "orderedList",
        "listItem",
        "horizontalRule",
    }
)

MARKS = frozenset({"bold", "italic", "strike", "code"})

# Blocks that contain inline content directly, as opposed to other blocks.
LEAF_BLOCKS = frozenset({"paragraph", "heading", "codeBlock"})


def normalize_attrs(attrs: dict[str, Any] | None) -> dict[str, Any]:
    """Drop ``None`` values and coerce numeric strings to their native type.

    The coercion is what keeps `heading level` an int on the wire; see module
    docstring for why that matters.
    """
    if not attrs:
        return {}
    out: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, str) and value.lstrip("-").isdigit():
            out[key] = int(value)
        else:
            out[key] = value
    return out
