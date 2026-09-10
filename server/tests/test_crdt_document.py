"""The CRDT layer: structure, markdown, and behaviour under concurrent edits."""

from __future__ import annotations

from pycrdt import XmlElement, XmlText

from coverse.crdt.document import CoverseDoc, get_int_attr, parse_markdown_blocks
from coverse.crdt.edits import StreamTarget, rewrite_document
from coverse.crdt.positions import TextAnchor, replace_range, resolve_text_anchor


def test_heading_level_is_stored_as_a_number():
    """Yjs attributes are typed. A string level would corrupt the browser's schema."""
    doc = CoverseDoc()
    doc.append_block("heading", "Title", {"level": 3})
    assert get_int_attr(doc.fragment.children[0], "level", 1) == 3
    assert doc.to_markdown().startswith("### ")


def test_markdown_round_trips_through_the_crdt():
    source = "# Title\n\nA paragraph.\n\n- one\n- two\n\n```py\nx = 1\n```\n\n> quoted"
    doc = CoverseDoc()
    doc.append_markdown(source)
    assert doc.to_markdown() == source


def test_parse_markdown_blocks_recognises_each_block_type():
    tags = [tag for tag, _, _ in parse_markdown_blocks("# h\n\ntext\n\n- a\n\n1. b\n\n> q\n\n---")]
    assert tags == [
        "heading",
        "paragraph",
        "bulletList",
        "orderedList",
        "blockquote",
        "horizontalRule",
    ]


def test_element_handle_survives_concurrent_structural_edits():
    """The AI keeps writing into its own block while humans edit around it."""
    doc = CoverseDoc()
    target = StreamTarget.append_to(doc)
    target.append("AI text")

    # A human inserts blocks above the AI's paragraph.
    with doc.doc.transaction():
        doc.fragment.children.insert(0, XmlElement("heading", {"level": 1}, [XmlText("Human")]))
        doc.fragment.children.insert(1, XmlElement("paragraph", None, [XmlText("More human")]))

    target.append(" continues")
    target.finish()

    assert "AI text continues" in doc.to_xml()
    assert doc.to_xml().index("Human") < doc.to_xml().index("AI text")


def test_streamed_markdown_gains_structure_per_block():
    doc = CoverseDoc()
    target = StreamTarget.append_to(doc)
    for chunk in ["## Heading", "\n\n", "Body text.", "\n\n", "- a\n- b"]:
        target.append(chunk)
    target.finish()

    xml = doc.to_xml()
    assert "<heading" in xml and "<bulletList>" in xml
    # The literal markdown must not survive as text.
    assert "##" not in xml


def test_stream_target_drops_a_trailing_empty_block():
    doc = CoverseDoc()
    target = StreamTarget.append_to(doc)
    target.append("Done.\n\n")
    target.finish()
    assert len(doc.fragment.children) == 1


def test_text_anchor_survives_a_shift_and_refuses_when_gone():
    doc = CoverseDoc()
    doc.append_block("paragraph", "The quick brown fox jumps.")
    node = doc.fragment.children[0].children[0]

    anchor = TextAnchor("brown fox", 10)
    node.insert(0, "PREFIX ")  # concurrent edit shifts the range

    resolved = resolve_text_anchor(node, anchor)
    assert resolved is not None
    start, end = resolved
    assert str(node)[start:end] == "brown fox"

    replace_range(node, start, end, "lazy dog")
    assert "lazy dog" in str(node)
    assert resolve_text_anchor(node, TextAnchor("not present", 0)) is None


def test_rewrite_document_replaces_the_body():
    doc = CoverseDoc()
    doc.append_markdown("# Old\n\nOld body.")
    rewrite_document(doc, "# New\n\nNew body.")
    assert "Old" not in doc.to_markdown()
    assert doc.to_markdown() == "# New\n\nNew body."


def test_updates_merge_between_two_replicas():
    """Two replicas edited independently converge on the same state."""
    a = CoverseDoc()
    a.append_block("paragraph", "from A")
    b = CoverseDoc()
    b.apply_update(a.encode_update())
    b.append_block("paragraph", "from B")
    a.apply_update(b.encode_update())

    assert a.to_xml() == b.to_xml()
    assert "from A" in a.to_xml() and "from B" in a.to_xml()
