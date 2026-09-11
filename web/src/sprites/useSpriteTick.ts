import { useEffect, useState } from 'react'

/**
 * One clock for every sprite on screen.
 *
 * A dozen sprites each running their own interval would mean a dozen timers and
 * a dozen re-renders a second. This is a single subscription that every sprite
 * reads, and it stops entirely when nothing is mounted.
 */
const listeners = new Set<(tick: number) => void>()
let timer: number | null = null
let tick = 0

function start() {
  if (timer !== null) return
  timer = window.setInterval(() => {
    tick += 1
    for (const listener of listeners) listener(tick)
  }, 420)
}

function stop() {
  if (timer !== null && listeners.size === 0) {
    window.clearInterval(timer)
    timer = null
  }
}

export function useSpriteTick(): number {
  const [value, setValue] = useState(tick)

  useEffect(() => {
    listeners.add(setValue)
    start()
    return () => {
      listeners.delete(setValue)
      stop()
    }
  }, [])

  return value
}
