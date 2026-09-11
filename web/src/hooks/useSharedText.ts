/**
 * Binds a Y.Text to a plain textarea so several people can type into one box.
 *
 * The naive version (set value from the Y.Text on every change) destroys the
 * caret: the browser puts it at the end whenever value is assigned, so your
 * cursor jumps every time somebody else types a character. Two things fix it.
 *
 * Local edits are diffed rather than replaced. The common prefix and suffix are
 * found and only the changed span is applied to the Y.Text, so a one character
 * insert becomes a one character CRDT operation and merges cleanly with a
 * simultaneous edit somewhere else in the box.
 *
 * Remote edits map the caret. Before writing the new value we note where the
 * selection is, then shift it by how much text changed before it, so the caret
 * stays attached to the same words rather than the same offset.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type * as Y from 'yjs'

function commonPrefix(a: string, b: string): number {
  const max = Math.min(a.length, b.length)
  let i = 0
  while (i < max && a[i] === b[i]) i += 1
  return i
}

function commonSuffix(a: string, b: string, prefix: number): number {
  const max = Math.min(a.length, b.length) - prefix
  let i = 0
  while (i < max && a[a.length - 1 - i] === b[b.length - 1 - i]) i += 1
  return i
}

export function useSharedText(text: Y.Text | null) {
  const ref = useRef<HTMLTextAreaElement | null>(null)
  const [value, setValue] = useState(() => text?.toString() ?? '')
  // Set while we are the origin of a change, so the observer does not fight us.
  const applying = useRef(false)

  useEffect(() => {
    if (!text) return

    const onChange = () => {
      if (applying.current) return
      const next = text.toString()
      const element = ref.current

      if (!element || document.activeElement !== element) {
        setValue(next)
        return
      }

      // Keep the caret on the same characters rather than the same index.
      const previous = element.value
      const start = element.selectionStart ?? 0
      const end = element.selectionEnd ?? 0
      const prefix = commonPrefix(previous, next)
      const delta = next.length - previous.length

      const shift = (position: number) => (position <= prefix ? position : position + delta)

      setValue(next)
      requestAnimationFrame(() => {
        if (ref.current && document.activeElement === ref.current) {
          const nextStart = Math.max(0, Math.min(shift(start), next.length))
          const nextEnd = Math.max(0, Math.min(shift(end), next.length))
          ref.current.setSelectionRange(nextStart, nextEnd)
        }
      })
    }

    text.observe(onChange)
    setValue(text.toString())
    return () => text.unobserve(onChange)
  }, [text])

  const onInput = useCallback(
    (next: string) => {
      setValue(next)
      if (!text) return

      const previous = text.toString()
      if (previous === next) return

      const prefix = commonPrefix(previous, next)
      const suffix = commonSuffix(previous, next, prefix)
      const removed = previous.length - prefix - suffix
      const inserted = next.slice(prefix, next.length - suffix)

      applying.current = true
      try {
        text.doc?.transact(() => {
          if (removed > 0) text.delete(prefix, removed)
          if (inserted) text.insert(prefix, inserted)
        })
      } finally {
        applying.current = false
      }
    },
    [text],
  )

  return { ref, value, onInput }
}
