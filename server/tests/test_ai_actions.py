"""AI actions: what each one does to the document, and what it must not do."""

from __future__ import annotations

import pytest

from coverse.ai import actions
from coverse.ai.base import Delta, Message, Provider, ProviderError
from coverse.ai.mock import MockProvider
from coverse.crdt import suggestions as suggestion_store
from coverse.crdt.document import CoverseDoc


class ScriptedProvider(Provider):
    """Yields exactly what it is told, so tests assert on real output."""

    name = "scripted"

    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls: list[list[Message]] = []

    async def stream(self, messages, **opts):
        self.calls.append(messages)
        for chunk in self.chunks:
            yield Delta(text=chunk)
        yield Delta(done=True)


async def test_generate_writes_structured_content_into_the_document():
    doc = CoverseDoc()
    provider = ScriptedProvider(["## Heading", "\n\n", "Body text here."])

    events = await actions.collect(
        actions.generate(provider=provider, doc=doc, instruction="write", author="u1", flush_ms=0)
    )

    assert events[-1]["type"] == "done"
    assert "<heading" in doc.to_xml()
    assert "Body text here." in doc.to_xml()


async def test_generate_sees_the_existing_document_as_context():
    doc = CoverseDoc()
    doc.append_block("paragraph", "Existing content.")
    provider = ScriptedProvider(["ok"])

    await actions.collect(
        actions.generate(
            provider=provider, doc=doc, instruction="continue", author="u1", flush_ms=0
        )
    )

    assert "Existing content." in provider.calls[0][-1].content


async def test_rewrite_creates_a_suggestion_and_leaves_the_body_alone():
    doc = CoverseDoc()
    doc.append_block("paragraph", "The original sentence.")
    before = doc.to_xml()
    provider = ScriptedProvider(["A punchier sentence."])

    events = await actions.collect(
        actions.rewrite(
            provider=provider,
            doc=doc,
            selection="The original sentence.",
            instruction="punchier",
            author="u1",
        )
    )

    assert doc.to_xml() == before, "rewrite must not touch the document body"
    pending = suggestion_store.list_pending(doc.suggestions)
    assert len(pending) == 1
    assert pending[0]["kind"] == "rewrite"
    assert pending[0]["replacement"] == "A punchier sentence."
    assert events[-1]["id"] == pending[0]["id"]


async def test_comment_creates_a_comment_suggestion_without_editing():
    doc = CoverseDoc()
    doc.append_block("paragraph", "A passage.")
    before = doc.to_xml()

    await actions.collect(
        actions.comment(
            provider=ScriptedProvider(["Consider leading with the claim."]),
            doc=doc,
            selection="A passage.",
            author="u1",
        )
    )

    assert doc.to_xml() == before
    pending = suggestion_store.list_pending(doc.suggestions)
    assert pending[0]["kind"] == "comment"
    assert pending[0]["body"] == "Consider leading with the claim."


async def test_ask_never_touches_the_document():
    doc = CoverseDoc()
    doc.append_block("paragraph", "Some content.")
    before = doc.to_xml()

    events = await actions.collect(
        actions.ask(provider=ScriptedProvider(["The answer."]), doc=doc, question="what?")
    )

    assert doc.to_xml() == before
    assert events[-1]["answer"] == "The answer."
    assert not suggestion_store.list_pending(doc.suggestions)


async def test_canvas_replaces_the_whole_document():
    doc = CoverseDoc()
    doc.append_markdown("# Old\n\nOld body.")

    await actions.collect(
        actions.canvas(
            provider=ScriptedProvider(["# New\n\nNew body."]),
            doc=doc,
            instruction="redo",
            flush_ms=0,
        )
    )

    assert doc.to_markdown() == "# New\n\nNew body."


async def test_rewrite_rejects_an_empty_model_response():
    doc = CoverseDoc()
    with pytest.raises(ProviderError):
        await actions.collect(
            actions.rewrite(
                provider=ScriptedProvider(["   "]),
                doc=doc,
                selection="x",
                instruction="",
                author="u1",
            )
        )


async def test_delta_batcher_flushes_on_sentence_boundaries():
    batcher = actions.DeltaBatcher(flush_ms=10_000)  # timer will not fire
    assert batcher.add("Hello") is None
    assert batcher.add(" world") is None
    assert batcher.add(". ") == "Hello world. "


async def test_mock_provider_routes_on_the_action_hint_not_the_prompt_text():
    """The system prompts share vocabulary, so substring sniffing is unreliable."""
    provider = MockProvider(delay_ms=0)
    rewritten = await provider.complete([Message("user", 'rewrite """this"""')], action="rewrite")
    generated = await provider.complete([Message("user", "a topic")], action="generate")
    assert "rewritten for clarity" in rewritten
    assert "rewritten for clarity" not in generated


async def test_mock_provider_can_be_told_to_fail():
    provider = MockProvider(delay_ms=0)
    with pytest.raises(ProviderError):
        await provider.complete([Message("user", "__fail__")])
