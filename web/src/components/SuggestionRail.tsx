import type { Suggestion } from '../lib/types'

interface SuggestionRailProps {
  suggestions: Suggestion[]
  activeId: string | null
  staleIds: Set<string>
  onFocus: (id: string) => void
  onAccept: (suggestion: Suggestion) => void
  onReject: (suggestion: Suggestion) => void
}

/**
 * The margin rail of pending AI suggestions.
 *
 * Suggestions live in the shared CRDT map, so this list is the same for every
 * person in the document and anyone can resolve an item.
 */
export function SuggestionRail({
  suggestions,
  activeId,
  staleIds,
  onFocus,
  onAccept,
  onReject,
}: SuggestionRailProps) {
  if (suggestions.length === 0) {
    return (
      <aside className="rail">
        <h2>Suggestions</h2>
        <p className="rail-empty">
          Select text and choose Rewrite or Review to get a suggestion here.
        </p>
      </aside>
    )
  }

  return (
    <aside className="rail">
      <h2>Suggestions</h2>
      {suggestions.map((suggestion) => {
        const stale = staleIds.has(suggestion.id)
        return (
          <article
            key={suggestion.id}
            className={`rail-card${suggestion.id === activeId ? ' is-active' : ''}${stale ? ' is-stale' : ''}`}
            onMouseEnter={() => onFocus(suggestion.id)}
          >
            <header>
              <span className="rail-kind">
                {suggestion.kind === 'rewrite' ? 'Rewrite' : 'Comment'}
              </span>
              {stale ? <span className="rail-stale">text changed</span> : null}
            </header>

            {suggestion.kind === 'rewrite' ? (
              <>
                <p className="rail-original">{suggestion.original}</p>
                <p className="rail-replacement">{suggestion.replacement}</p>
              </>
            ) : (
              <p className="rail-comment">{suggestion.body}</p>
            )}

            <footer>
              {suggestion.kind === 'rewrite' ? (
                <button
                  type="button"
                  onClick={() => onAccept(suggestion)}
                  disabled={stale}
                  title={stale ? 'The original text no longer exists' : 'Apply this rewrite'}
                >
                  Accept
                </button>
              ) : null}
              <button type="button" className="secondary" onClick={() => onReject(suggestion)}>
                Dismiss
              </button>
            </footer>
          </article>
        )
      })}
    </aside>
  )
}
