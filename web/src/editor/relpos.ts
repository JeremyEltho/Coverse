/**
 * Relative positions: how a suggestion survives concurrent editing.
 *
 * A selection captured now may not correspond to the same characters by the time
 * the model answers, because other people keep typing. Yjs relative positions
 * solve exactly this: they anchor to the CRDT item identity rather than to an
 * index, so they still resolve correctly after arbitrary concurrent edits.
 *
 * They are created and resolved here on the client. The server stores them as
 * opaque strings -- it never needs to interpret them, because accepting a
 * suggestion is a client-side edit through TipTap.
 */
import type { Editor } from '@tiptap/react'
import {
  absolutePositionToRelativePosition,
  relativePositionToAbsolutePosition,
  ySyncPluginKey,
} from '@tiptap/y-tiptap'
import * as Y from 'yjs'

export interface RelPos {
  from: string
  to: string
}

function encode(position: Y.RelativePosition): string {
  return btoa(String.fromCharCode(...Y.encodeRelativePosition(position)))
}

function decode(encoded: string): Y.RelativePosition {
  const binary = atob(encoded)
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
  return Y.decodeRelativePosition(bytes)
}

/** Capture the current selection as a pair of relative positions. */
export function captureSelection(editor: Editor): RelPos | null {
  const state = ySyncPluginKey.getState(editor.state)
  if (!state?.binding) return null

  const { from, to } = editor.state.selection
  if (from === to) return null

  const { type, binding } = state
  return {
    from: encode(absolutePositionToRelativePosition(from, type, binding.mapping)),
    to: encode(absolutePositionToRelativePosition(to, type, binding.mapping)),
  }
}

/**
 * Resolve a stored selection back to document positions.
 *
 * Returns null when the anchored text has been deleted, in which case the
 * suggestion is stale and must be dropped rather than applied somewhere wrong.
 */
export function resolveSelection(editor: Editor, relpos: RelPos): { from: number; to: number } | null {
  const state = ySyncPluginKey.getState(editor.state)
  if (!state?.binding) return null

  const { type, binding } = state
  const doc = type.doc
  if (!doc) return null

  const from = relativePositionToAbsolutePosition(doc, type, decode(relpos.from), binding.mapping)
  const to = relativePositionToAbsolutePosition(doc, type, decode(relpos.to), binding.mapping)

  if (from === null || to === null) return null
  if (from === to) return null
  return { from: Math.min(from, to), to: Math.max(from, to) }
}

/** A plain-text fallback anchor, for the server and for diagnostics. */
export function captureAnchor(editor: Editor): { text: string; offset: number } {
  const { from, to } = editor.state.selection
  return {
    text: editor.state.doc.textBetween(from, to, '\n'),
    offset: from,
  }
}
