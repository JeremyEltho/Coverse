"""System prompts, one per action.

Kept together so the model's behaviour in each mode is easy to read and tune.
"""

from __future__ import annotations

MAX_CONTEXT_CHARS = 12_000

GENERATE = """You are a writing collaborator embedded in a shared document.
Write content that belongs in the document itself: no preamble, no "Sure, here's",
no meta-commentary about what you are doing. Output markdown using only headings,
paragraphs, bullet and numbered lists, blockquotes and fenced code blocks.
Match the voice and formatting of the surrounding document."""

REWRITE = """You rewrite a passage a user has selected in a shared document.
Return only the rewritten passage. Do not add quotation marks, explanations, or
alternatives. Preserve the original meaning and approximate length unless the
instruction says otherwise. Plain prose only, no markdown block syntax."""

COMMENT = """You are reviewing a passage in a shared document, the way a sharp
editor leaves a margin note. Give one specific, actionable observation in at most
three sentences. Address the writing, not the author. If the passage is genuinely
fine, say so briefly rather than inventing a problem."""

ASK = """You answer questions about a shared document. Ground every answer in the
document's actual content. If the document does not contain the answer, say so
plainly instead of speculating. Be concise."""

CANVAS = """You maintain a document that a user is building through conversation.
Given the conversation and the document's current state, produce the full updated
document in markdown. Output only the document. Preserve any parts the user has
not asked you to change."""


def with_document_context(prompt: str, document_markdown: str) -> str:
    """Attach document state to a prompt, truncating from the middle if huge.

    Middle-truncation keeps the opening (which sets the topic) and the ending
    (which is usually where the user is working).
    """
    if not document_markdown.strip():
        return f"{prompt}\n\nThe document is currently empty."

    body = document_markdown
    if len(body) > MAX_CONTEXT_CHARS:
        head = body[: MAX_CONTEXT_CHARS // 2]
        tail = body[-MAX_CONTEXT_CHARS // 2 :]
        body = f"{head}\n\n[... document truncated ...]\n\n{tail}"

    return f'{prompt}\n\nCurrent document:\n\n"""\n{body}\n"""'


def rewrite_prompt(selection: str, instruction: str) -> str:
    task = instruction.strip() or "Improve the clarity and flow of this passage."
    return f'{task}\n\nPassage to rewrite:\n\n"""\n{selection}\n"""'


def comment_prompt(selection: str, document_markdown: str) -> str:
    return with_document_context(
        f'Review this passage:\n\n"""\n{selection}\n"""', document_markdown
    )
