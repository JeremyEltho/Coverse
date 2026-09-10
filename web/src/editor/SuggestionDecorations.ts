/**
 * Renders pending AI suggestions as decorations.
 *
 * Nothing here touches the document. A rewrite shows the original struck
 * through with the proposal beside it; a comment highlights its passage. The
 * document only changes if a human accepts, which is what makes AI edits
 * reviewable rather than something you have to undo.
 *
 * The suggestion list is pushed in through transaction metadata and kept in
 * ProseMirror plugin state. Mutating the extension's `options` object does not
 * work: the manager configures its own copy, so the plugin closure never sees
 * the change.
 */
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import type { Editor } from '@tiptap/react'
import type { Suggestion } from '../lib/types'
import { resolveSelection } from './relpos'

export const suggestionPluginKey = new PluginKey<SuggestionState>('coverseSuggestions')

export interface SuggestionState {
  suggestions: Suggestion[]
  activeId: string | null
}

const EMPTY: SuggestionState = { suggestions: [], activeId: null }

/** Push the current suggestions into the editor's plugin state. */
export function setSuggestionState(editor: Editor, next: SuggestionState): void {
  const current = suggestionPluginKey.getState(editor.state) ?? EMPTY
  // Avoid dispatching when nothing changed, or every render costs a transaction.
  if (
    current.activeId === next.activeId &&
    current.suggestions.length === next.suggestions.length &&
    current.suggestions.every((s, i) => s.id === next.suggestions[i]?.id)
  ) {
    return
  }
  editor.view.dispatch(editor.state.tr.setMeta(suggestionPluginKey, next))
}

function build(editor: Editor, state: SuggestionState, docState: EditorState): DecorationSet {
  const decorations: Decoration[] = []

  for (const suggestion of state.suggestions) {
    if (suggestion.status !== 'pending' || !suggestion.relpos) continue

    // Re-resolved against the live document every time: the anchored text may
    // have moved since the suggestion was made.
    const range = resolveSelection(editor, suggestion.relpos)
    if (!range) continue // the text is gone; the rail marks it stale

    const isActive = suggestion.id === state.activeId

    if (suggestion.kind === 'rewrite') {
      decorations.push(
        Decoration.inline(range.from, range.to, {
          class: `suggestion-original${isActive ? ' is-active' : ''}`,
        }),
      )
      if (suggestion.replacement) {
        decorations.push(
          Decoration.widget(
            range.to,
            () => {
              const span = document.createElement('span')
              span.className = `suggestion-replacement${isActive ? ' is-active' : ''}`
              span.textContent = suggestion.replacement ?? ''
              return span
            },
            { side: 1 },
          ),
        )
      }
    } else {
      decorations.push(
        Decoration.inline(range.from, range.to, {
          class: `suggestion-commented${isActive ? ' is-active' : ''}`,
        }),
      )
    }
  }

  return DecorationSet.create(docState.doc, decorations)
}

export const SuggestionDecorations = Extension.create({
  name: 'coverseSuggestions',

  addProseMirrorPlugins() {
    const extension = this

    return [
      new Plugin<SuggestionState>({
        key: suggestionPluginKey,
        state: {
          init: () => EMPTY,
          apply(transaction: Transaction, value: SuggestionState): SuggestionState {
            return transaction.getMeta(suggestionPluginKey) ?? value
          },
        },
        props: {
          decorations(this: Plugin<SuggestionState>, docState: EditorState) {
            const editor = extension.editor as Editor | undefined
            const state = this.getState(docState)
            if (!editor || !state || state.suggestions.length === 0) return DecorationSet.empty
            return build(editor, state, docState)
          },
        },
      }),
    ]
  },
})
