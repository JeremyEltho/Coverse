"""The primitives the AI uses to change a document.

Every write here goes through a pycrdt transaction on the server's live replica,
so it reaches clients through ordinary Yjs sync and merges against concurrent
human typing. There is no bespoke "AI edit" message and no string splicing.
"""

from __future__ import annotations

from typing import Any

from pycrdt import XmlElement, XmlText

from .document import CoverseDoc, as_text, parse_markdown_blocks
from .schema import normalize_attrs


class StreamTarget:
    """An append-only cursor into one block, used while a model streams.

    Holds a live handle to its own ``XmlElement``. Because pycrdt handles stay
    valid when other clients insert or delete siblings, the AI can keep writing
    into the right place no matter what humans do to the rest of the document.

    Deltas are appended at the end of the block's text. When a delta contains a
    blank line the target rolls over into a fresh block, so streamed markdown
    grows real structure instead of one giant paragraph.
    """

    def __init__(self, doc: CoverseDoc, element: XmlElement, tag: str = "paragraph") -> None:
        self._doc = doc
        self._element = element
        self._tag = tag
        self._written = 0

    @classmethod
    def append_to(
        cls, doc: CoverseDoc, tag: str = "paragraph", attrs: dict[str, Any] | None = None
    ) -> StreamTarget:
        element = doc.append_block(tag, "", attrs)
        return cls(doc, element, tag)

    @property
    def element(self) -> XmlElement:
        return self._element

    @property
    def written(self) -> int:
        return self._written

    def _text_node(self) -> XmlText:
        children = self._element.children
        if len(children) == 0:
            with self._doc.doc.transaction():
                children.append(XmlText(""))
        return as_text(children[0])

    def append(self, delta: str) -> None:
        """Append a chunk of streamed text, starting new blocks on blank lines."""
        if not delta:
            return
        self._written += len(delta)

        # A blank line means the model finished a block; roll over so the next
        # text lands in a new paragraph rather than extending the current one.
        if "\n\n" in delta:
            head, _, tail = delta.partition("\n\n")
            if head:
                self._append_raw(head)
            self._start_new_block()
            if tail:
                self.append(tail)
            return

        self._append_raw(delta)

    def _append_raw(self, text: str) -> None:
        node = self._text_node()
        with self._doc.doc.transaction():
            node.insert(len(str(node)), text)

    def _start_new_block(self) -> None:
        self._finalize_block()
        self._element = self._doc.append_block("paragraph", "")
        self._tag = "paragraph"

    def _finalize_block(self) -> None:
        """Give the just-completed block its real structure.

        Text streams in as a plain paragraph so it appears the instant the model
        emits it. Once the block is complete its markdown is unambiguous, so it
        is re-parsed and, if it turns out to be a heading, list, quote or code
        block, swapped for the correct node. Doing this per block rather than
        once at the end keeps the document structurally correct as it grows,
        instead of reflowing everything when the stream finishes.
        """
        text = self.current_text()
        if not text.strip():
            return

        blocks = parse_markdown_blocks(text)
        # Nothing to do if it really was just a paragraph.
        if len(blocks) == 1 and blocks[0][0] == "paragraph" and not blocks[0][2]:
            return

        fragment = self._doc.fragment
        index = self._index_of(self._element)
        if index is None:
            return

        with self._doc.doc.transaction():
            del fragment.children[index]
            for offset, (tag, block_text, attrs) in enumerate(blocks):
                fragment.children.insert(index + offset, _build_element(tag, block_text, attrs))

    def _index_of(self, element: XmlElement) -> int | None:
        fragment = self._doc.fragment
        for index in range(len(fragment.children)):
            if fragment.children[index] == element:
                return index
        return None

    def current_text(self) -> str:
        return str(self._text_node())

    def finish(self) -> None:
        """Structure the final block, or drop it if the stream ended empty."""
        if self.current_text().strip():
            self._finalize_block()
            return

        fragment = self._doc.fragment
        index = self._index_of(self._element)
        if index is not None:
            with self._doc.doc.transaction():
                del fragment.children[index]


def _build_element(tag: str, text: str, attrs: dict[str, Any] | None) -> XmlElement:
    """Construct a node for the TipTap schema, expanding list items."""
    if tag in ("bulletList", "orderedList"):
        items = [
            XmlElement("listItem", None, [XmlElement("paragraph", None, [XmlText(line)])])
            for line in text.split("\n")
        ]
        return XmlElement(tag, normalize_attrs(attrs), items)
    return XmlElement(tag, normalize_attrs(attrs), [XmlText(text)])


def replace_block_with_markdown(doc: CoverseDoc, index: int, markdown: str) -> None:
    """Swap a single block for the blocks parsed out of ``markdown``."""
    fragment = doc.fragment
    if not 0 <= index < len(fragment.children):
        raise IndexError(index)
    with doc.doc.transaction():
        del fragment.children[index]
        for offset, (tag, text, attrs) in enumerate(parse_markdown_blocks(markdown)):
            fragment.children.insert(index + offset, _build_element(tag, text, attrs))


def rewrite_document(doc: CoverseDoc, markdown: str) -> None:
    """Replace the whole document body. Used by Canvas mode regeneration."""
    with doc.doc.transaction():
        doc.clear()
        doc.append_markdown(markdown)
