import { useMemo } from 'react'
import { GRID, spriteById, type SpriteDef } from './catalogue'

export type SpriteState = 'idle' | 'typing' | 'talking' | 'thinking' | 'still'

interface SpriteProps {
  id?: string
  def?: SpriteDef
  size?: number
  state?: SpriteState
  title?: string
  className?: string
}

interface Run {
  x: number
  y: number
  width: number
  color: string
}

/**
 * Turn a pixel grid into rects, merging horizontal runs of the same colour.
 *
 * A 14x14 creature is up to 196 pixels but only around 40 runs, and a room can
 * have a dozen sprites on screen at once, so the merge is worth the few lines.
 */
function toRuns(def: SpriteDef): Run[] {
  const runs: Run[] = []

  def.rows.forEach((row, y) => {
    let start = -1
    let code = '.'

    const flush = (end: number) => {
      if (start >= 0 && code !== '.') {
        runs.push({
          x: start,
          y,
          width: end - start,
          color: def.palette[Number(code)] ?? 'transparent',
        })
      }
      start = -1
    }

    for (let x = 0; x < row.length; x += 1) {
      const char = row[x]
      if (char !== code) {
        flush(x)
        if (char !== '.') {
          start = x
          code = char
        } else {
          code = '.'
        }
      }
    }
    flush(row.length)
  })

  return runs
}

export function Sprite({
  id,
  def,
  size = 28,
  state = 'idle',
  title,
  className = '',
}: SpriteProps) {
  const sprite = def ?? spriteById(id)
  const runs = useMemo(() => toRuns(sprite), [sprite])

  return (
    <svg
      className={`sprite is-${state} ${className}`}
      width={size}
      height={size}
      viewBox={`0 0 ${GRID} ${GRID}`}
      shapeRendering="crispEdges"
      role="img"
      aria-label={title ?? sprite.name}
    >
      {title ? <title>{title}</title> : null}
      {runs.map((run, index) => (
        <rect
          key={index}
          x={run.x}
          y={run.y}
          width={run.width}
          height={1}
          fill={run.color}
        />
      ))}
    </svg>
  )
}
