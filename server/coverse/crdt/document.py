"""A wrapper around a pycrdt `Doc` that speaks ProseMirror.

`CoverseDoc` owns the shared types for one document:

* ``default``      -- the XmlFragment the TipTap editor binds to
* ``suggestions``  -- a Map of pending AI suggestions (see suggestions.py)
* ``meta``         -- a Map of document metadata (title, mode)

All mutations happen inside pycrdt transactions, so they merge correctly against
concurrent edits from any human client.
"""

from __future__ import annotations

import re
from typing import Any

from pycrdt import Doc, Map, XmlElement, XmlFragment, XmlText

from .schema import LEAF_BLOCKS, normalize_attrs

FRAGMENT_NAME = "default"
SUGGESTIONS_NAME = "suggestions"
META_NAME = "meta"


class CoverseDoc:
    """The server's live replica of one collaborative document."""

    def __init__(self, doc: Doc | None = None) -> None:
        self.doc = doc or Doc()
        # Assigning a root type is idempotent-ish in pycrdt: the same name always
        # resolves to the same underlying type, so this is safe on a loaded doc.
        self.doc[FRAGMENT_NAME] = XmlFragment()
        self.doc[SUGGESTIONS_NAME] = Map()
        self.doc[META_NAME] = Map()

    # --- shared type accessors -------------------------------------------------

    @property
    def fragment(self) -> XmlFragment:
        return self.doc[FRAGMENT_NAME]

    @property
    def suggestions(self) -> Map:
        return self.doc[SUGGESTIONS_NAME]

    @property
    def meta(self) -> Map:
        return self.doc[META_NAME]

    # --- state transfer --------------------------------------------------------

    def state_vector(self) -> bytes:
        return self.doc.get_state()

    def encode_update(self, state: bytes | None = None) -> bytes:
        """Full state as a single update, or a diff since ``state``."""
        return self.doc.get_update(state) if state else self.doc.get_update()

    def apply_update(self, update: bytes) -> None:
        self.doc.apply_update(update)

    # --- reading ---------------------------------------------------------------

    def to_xml(self) -> str:
        return str(self.fragment)

    def to_markdown(self) -> str:
        """Serialize the document for use as LLM context.

        Deliberately lossy: the model needs readable structure, not fidelity.
        """
        return "\n\n".join(
            block for block in (_block_to_markdown(c) for c in self.fragment.children) if block
        )

    def text_length(self) -> int:
        return sum(_node_text_length(child) for child in self.fragment.children)

    def is_empty(self) -> bool:
        return len(self.fragment.children) == 0 or self.text_length() == 0

    # --- writing ---------------------------------------------------------------

    def append_block(
        self, tag: str, text: str = "", attrs: dict[str, Any] | None = None
    ) -> XmlElement:
        """Append a single leaf block (paragraph, heading, codeBlock) at the end."""
        with self.doc.transaction():
            element = XmlElement(tag, normalize_attrs(attrs), [XmlText(text)])
            self.fragment.children.append(element)
            return as_element(self.fragment.children[len(self.fragment.children) - 1])

    def insert_block_at(
        self, index: int, tag: str, text: str = "", attrs: dict[str, Any] | None = None
    ) -> XmlElement:
        with self.doc.transaction():
            index = max(0, min(index, len(self.fragment.children)))
            element = XmlElement(tag, normalize_attrs(attrs), [XmlText(text)])
            self.fragment.children.insert(index, element)
            return as_element(self.fragment.children[index])

    def append_markdown(self, markdown: str) -> list[XmlElement]:
        """Parse a small subset of markdown into blocks and append them.

        Supports headings, bullet/ordered lists, blockquotes, fenced code and
        paragraphs -- enough for what a model actually emits.
        """
        created: list[XmlElement] = []
        with self.doc.transaction():
            for tag, text, attrs in parse_markdown_blocks(markdown):
                if tag in ("bulletList", "orderedList"):
                    items = [
                        XmlElement("listItem", None, [XmlElement("paragraph", None, [XmlText(i)])])
                        for i in text.split("\n")
                    ]
                    element = XmlElement(tag, normalize_attrs(attrs), items)
                else:
                    element = XmlElement(tag, normalize_attrs(attrs), [XmlText(text)])
                self.fragment.children.append(element)
                created.append(as_element(self.fragment.children[len(self.fragment.children) - 1]))
        return created

    def block_at(self, index: int) -> XmlElement | None:
        if 0 <= index < len(self.fragment.children):
            return as_element(self.fragment.children[index])
        return None

    def clear(self) -> None:
        with self.doc.transaction():
            while len(self.fragment.children) > 0:
                del self.fragment.children[0]


# --- helpers -------------------------------------------------------------------


def as_element(node: Any) -> XmlElement:
    """Narrow a child node to an XmlElement.

    Indexing `XmlFragment.children` yields a union of the three XML types. Every
    direct child of the fragment is an element in this schema, so this asserts
    that rather than letting a wrong type travel silently.
    """
    if not isinstance(node, XmlElement):
        raise TypeError(f"expected an XmlElement, got {type(node).__name__}")
    return node


def as_text(node: Any) -> XmlText:
    if not isinstance(node, XmlText):
        raise TypeError(f"expected an XmlText, got {type(node).__name__}")
    return node


def get_attr(node: Any, key: str, default: Any = None) -> Any:
    """Read one attribute off an XmlElement.

    pycrdt exposes attributes through an `XmlAttributesView` whose `get()` takes
    no default argument, and returns Yjs numbers as floats. Both of those bite
    if you treat it like a dict, so every attribute read goes through here.
    """
    attributes = getattr(node, "attributes", None)
    if attributes is None:
        return default
    try:
        value = attributes.get(key)
    except (TypeError, KeyError):
        return default
    return default if value is None else value


def get_int_attr(node: Any, key: str, default: int) -> int:
    value = get_attr(node, key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _node_text_length(node: Any) -> int:
    if isinstance(node, XmlText):
        return len(str(node))
    children = getattr(node, "children", None)
    if children is None:
        return 0
    return sum(_node_text_length(c) for c in children)


def _node_text(node: Any) -> str:
    if isinstance(node, XmlText):
        return str(node)
    children = getattr(node, "children", None)
    if children is None:
        return ""
    return "".join(_node_text(c) for c in children)


def _block_to_markdown(node: Any) -> str:
    tag = getattr(node, "tag", None)
    text = _node_text(node)
    if tag == "heading":
        level = get_int_attr(node, "level", 1)
        return f"{'#' * max(1, min(level, 6))} {text}"
    if tag == "codeBlock":
        language = get_attr(node, "language") or ""
        return f"```{language}\n{text}\n```"
    if tag == "blockquote":
        return "\n".join(f"> {line}" for line in text.splitlines() or [""])
    if tag == "bulletList":
        return "\n".join(f"- {_node_text(item)}" for item in node.children)
    if tag == "orderedList":
        return "\n".join(f"{i + 1}. {_node_text(item)}" for i, item in enumerate(node.children))
    if tag == "horizontalRule":
        return "---"
    return text


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")


def parse_markdown_blocks(markdown: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    """Turn markdown into ``(tag, text, attrs)`` triples for the TipTap schema."""
    blocks: list[tuple[str, str, dict[str, Any] | None]] = []
    lines = markdown.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            language = stripped[3:].strip() or None
            i += 1
            body: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence
            blocks.append(("codeBlock", "\n".join(body), {"language": language}))
            continue

        if stripped in ("---", "***", "___"):
            blocks.append(("horizontalRule", "", None))
            i += 1
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            blocks.append(("heading", heading.group(2), {"level": len(heading.group(1))}))
            i += 1
            continue

        if _BULLET_RE.match(line) or _ORDERED_RE.match(line):
            ordered = _ORDERED_RE.match(line) is not None
            items: list[str] = []
            while i < len(lines):
                match = _ORDERED_RE.match(lines[i]) if ordered else _BULLET_RE.match(lines[i])
                if not match:
                    break
                items.append(match.group(1))
                i += 1
            blocks.append(("orderedList" if ordered else "bulletList", "\n".join(items), None))
            continue

        if stripped.startswith(">"):
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(("blockquote", "\n".join(quote), None))
            continue

        para: list[str] = []
        while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
            para.append(lines[i].strip())
            i += 1
        blocks.append(("paragraph", " ".join(para), None))

    return blocks


def _is_block_start(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped.startswith("```")
        or stripped.startswith(">")
        or _HEADING_RE.match(stripped)
        or _BULLET_RE.match(line)
        or _ORDERED_RE.match(line)
        or stripped in ("---", "***", "___")
    )


__all__ = [
    "CoverseDoc",
    "as_element",
    "as_text",
    "FRAGMENT_NAME",
    "LEAF_BLOCKS",
    "get_attr",
    "get_int_attr",
    "parse_markdown_blocks",
]
