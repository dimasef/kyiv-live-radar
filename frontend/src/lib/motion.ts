import type { CSSProperties } from 'react'

/** Stagger delay for the `.rise` entrance animation (see index.css) — pass the
 * element's position in the reveal sequence. */
export function riseDelay(position: number): CSSProperties {
  return { '--i': position } as CSSProperties
}
