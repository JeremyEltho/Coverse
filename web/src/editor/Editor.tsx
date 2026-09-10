import { useEffect, useMemo } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Collaboration } from '@tiptap/extension-collaboration'
import { CollaborationCaret } from '@tiptap/extension-collaboration-caret'
import { Placeholder } from '@tiptap/extension-placeholder'
import type { WebsocketProvider } from 'y-websocket'
import type * as Y from 'yjs'
import type { Suggestion } from '../lib/types'
import { SuggestionDecorations, setSuggestionState } from './SuggestionDecorations'
import { SelectionMenu } from './SelectionMenu'

interface EditorProps {
  doc: Y.Doc
  provider: WebsocketProvider
  name: string
  color: string
  suggestions: Suggestion[]
  activeSuggestionId: string | null
  placeholder?: string
  editable?: boolean
  onEditorReady?: (editor: ReturnType<typeof useEditor>) => void
  onRewrite?: (selection: string) => void
  onComment?: (selection: string) => void
  onAsk?: (selection: string) => void
}

export function Editor({
  doc,
  provider,
  name,
  color,
  suggestions,
  activeSuggestionId,
  placeholder = 'Start writing, or type @ai to bring in the assistant.',
  editable = true,
  onEditorReady,
  onRewrite,
  onComment,
  onAsk,
}: EditorProps) {
  const extensions = useMemo(
    () => [
      // Collaboration owns document history, so StarterKit's own undo must go.
      StarterKit.configure({ undoRedo: false }),
      Collaboration.configure({ document: doc }),
      CollaborationCaret.configure({ provider, user: { name, color } }),
      Placeholder.configure({ placeholder }),
      SuggestionDecorations,
    ],
    [doc, provider, name, color, placeholder],
  )

  const editor = useEditor(
    { extensions, editable, editorProps: { attributes: { class: 'coverse-prose' } } },
    [extensions, editable],
  )

  // Feed current suggestions to the decoration plugin.
  useEffect(() => {
    if (!editor) return
    setSuggestionState(editor, { suggestions, activeId: activeSuggestionId })
  }, [editor, suggestions, activeSuggestionId])

  useEffect(() => {
    if (editor && onEditorReady) onEditorReady(editor)
  }, [editor, onEditorReady])

  if (!editor) return <div className="editor-loading">Connecting…</div>

  return (
    <div className="editor-surface">
      <SelectionMenu
        editor={editor}
        onRewrite={onRewrite}
        onComment={onComment}
        onAsk={onAsk}
      />
      <EditorContent editor={editor} />
    </div>
  )
}
