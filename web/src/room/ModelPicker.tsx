import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { ModelCatalogue, ModelInfo } from '../lib/types'

interface ModelPickerProps {
  current: string
  isDriver: boolean
  disabled: boolean
  onChoose: (id: string, name: string) => void
}

function price(model: ModelInfo): string {
  if (model.free) return 'free'
  const parts: string[] = []
  if (model.prompt_price != null) parts.push(`$${model.prompt_price}`)
  if (model.completion_price != null) parts.push(`$${model.completion_price}`)
  return parts.length ? `${parts.join(' / ')} per M` : ''
}

/**
 * Which model the room is talking to.
 *
 * The choice is shared, because there is one conversation and everyone should
 * know what is answering it. Only the driver can change it, for the same reason
 * only the driver can send: it decides what the next answer comes from.
 *
 * OpenRouter lists hundreds of models, so this filters as you type rather than
 * pretending a plain select would be usable.
 */
export function ModelPicker({ current, isDriver, disabled, onChoose }: ModelPickerProps) {
  const [catalogue, setCatalogue] = useState<ModelCatalogue | null>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api
      .listModels()
      .then(setCatalogue)
      .catch(() => setCatalogue(null))
  }, [])

  // Clicking away closes it, which a bare dropdown of 300 rows badly needs.
  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const models = catalogue?.models ?? []

  const label = useMemo(() => {
    const match = models.find((m) => m.id === current)
    if (match) return match.name
    // Before the catalogue loads, show the id rather than an empty control.
    return current || catalogue?.default || '…'
  }, [models, current, catalogue])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = q
      ? models.filter((m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q))
      : models
    return list.slice(0, 60)
  }, [models, query])

  // Nothing to switch between, so show the model as plain text.
  if (models.length <= 1) {
    return <span className="model-label">{label}</span>
  }

  if (!isDriver) {
    return (
      <span className="model-label" title="Only the person with the mic can change this">
        {label}
      </span>
    )
  }

  return (
    <div className="model-picker" ref={boxRef}>
      <button
        type="button"
        className="model-trigger"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        title={disabled ? 'Wait for the current reply to finish' : 'Change the model'}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="model-trigger-name">{label}</span>
        <svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
          <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>

      {open ? (
        <div className="model-menu" role="listbox">
          <input
            className="model-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Search ${models.length} models`}
            autoFocus
          />
          <div className="model-list">
            {filtered.length === 0 ? (
              <p className="panel-empty">Nothing matches that.</p>
            ) : (
              filtered.map((model) => (
                <button
                  type="button"
                  key={model.id}
                  role="option"
                  aria-selected={model.id === current}
                  className={`model-option${model.id === current ? ' is-current' : ''}`}
                  onClick={() => {
                    onChoose(model.id, model.name)
                    setOpen(false)
                    setQuery('')
                  }}
                >
                  <span className="model-option-name">{model.name}</span>
                  <span className="model-option-meta">
                    {price(model)}
                    {model.context_length
                      ? ` · ${Math.round(model.context_length / 1000)}k`
                      : ''}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
