import type { Editor } from '@tiptap/react'

const HEADINGS = [1, 2, 3] as const

export function Toolbar({ editor }: { editor: Editor | null }) {
  if (!editor) return <div className="toolbar" />

  const button = (
    label: string,
    isActive: boolean,
    onClick: () => void,
    title: string,
  ) => (
    <button
      key={title}
      type="button"
      className={isActive ? 'is-active' : ''}
      onClick={onClick}
      title={title}
    >
      {label}
    </button>
  )

  return (
    <div className="toolbar">
      {HEADINGS.map((level) =>
        button(
          `H${level}`,
          editor.isActive('heading', { level }),
          () => editor.chain().focus().toggleHeading({ level }).run(),
          `Heading ${level}`,
        ),
      )}
      <span className="toolbar-divider" />
      {button('B', editor.isActive('bold'), () => editor.chain().focus().toggleBold().run(), 'Bold')}
      {button('I', editor.isActive('italic'), () => editor.chain().focus().toggleItalic().run(), 'Italic')}
      {button('S', editor.isActive('strike'), () => editor.chain().focus().toggleStrike().run(), 'Strikethrough')}
      <span className="toolbar-divider" />
      {button('•', editor.isActive('bulletList'), () => editor.chain().focus().toggleBulletList().run(), 'Bullet list')}
      {button('1.', editor.isActive('orderedList'), () => editor.chain().focus().toggleOrderedList().run(), 'Numbered list')}
      {button('"', editor.isActive('blockquote'), () => editor.chain().focus().toggleBlockquote().run(), 'Quote')}
      {button('{ }', editor.isActive('codeBlock'), () => editor.chain().focus().toggleCodeBlock().run(), 'Code block')}
    </div>
  )
}
