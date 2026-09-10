import { BubbleMenu } from '@tiptap/react/menus'
import type { Editor } from '@tiptap/react'

interface SelectionMenuProps {
  editor: Editor
  onRewrite?: (selection: string) => void
  onComment?: (selection: string) => void
  onAsk?: (selection: string) => void
}

/**
 * The menu that appears over a selection.
 *
 * Formatting on the left, AI actions on the right. The AI actions read the
 * selected text and hand it up; capturing the relative position happens in the
 * mode component, which owns the socket.
 */
export function SelectionMenu({ editor, onRewrite, onComment, onAsk }: SelectionMenuProps) {
  const selectedText = () => {
    const { from, to } = editor.state.selection
    return editor.state.doc.textBetween(from, to, ' ').trim()
  }

  const run = (handler?: (selection: string) => void) => () => {
    const text = selectedText()
    if (text && handler) handler(text)
  }

  return (
    <BubbleMenu editor={editor} className="bubble-menu">
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleBold().run()}
        className={editor.isActive('bold') ? 'is-active' : ''}
        title="Bold"
      >
        B
      </button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleItalic().run()}
        className={editor.isActive('italic') ? 'is-active' : ''}
        title="Italic"
      >
        <em>I</em>
      </button>
      <button
        type="button"
        onClick={() => editor.chain().focus().toggleCode().run()}
        className={editor.isActive('code') ? 'is-active' : ''}
        title="Code"
      >
        {'</>'}
      </button>

      <span className="bubble-divider" />

      <button type="button" onClick={run(onRewrite)} title="Ask the AI to rewrite this">
        Rewrite
      </button>
      <button type="button" onClick={run(onComment)} title="Ask the AI to review this">
        Review
      </button>
      <button type="button" onClick={run(onAsk)} title="Ask the AI about this">
        Ask
      </button>
    </BubbleMenu>
  )
}
