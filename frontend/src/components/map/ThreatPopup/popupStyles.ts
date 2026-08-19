import type { CSSProperties } from 'react'

/** The popup lives inside Leaflet's own DOM, outside the app's styled tree, so
 * it styles itself inline rather than with utility classes (see
 * threatDisplay.tsx, whose `as`/`style` split exists for exactly this).
 *
 * The one deliberate exception is the home-distance/ETA pair, which reuses
 * HomeDistance's Tailwind tones so the two lines can't drift apart. */
export const MONO = 'IBM Plex Mono, monospace'

/** A metadata line inside a section. */
export const row: CSSProperties = { fontFamily: MONO, fontSize: 12, opacity: 0.75 }

export const HAIRLINE = 'rgba(255,255,255,0.1)'
