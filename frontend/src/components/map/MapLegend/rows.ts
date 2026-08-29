import { MUTED_COLOR, TYPE_COLORS } from '@/theme'
import { launcherGlyphSvg, threatGlyphSvg } from '@/threatIcons'
import { DOWN_LABEL_KEY } from '@/threatLabels'
import type { TargetType } from '@/types'

import { ZONE_ALL_CLEAR, ZONE_GLOW, ZONE_STYLES } from '../constants'

export const GLYPH_PX = 22

/** One row of the legend. `flipped` is the same thing in its opposite state — a
 * target shot down, a siren called off — and is what makes the row clickable.
 * A row without it (the launch site) simply has no opposite. */
export interface LegendRow {
  id: string
  labelKey: string
  html: string
  flipped?: { labelKey: string; html: string }
}

/** A raion's lit edge as a swatch. Drawn by hand rather than by borrowing the
 * real SVG filter — its blur is sized for a raion and would swallow a 16px
 * square whole. */
function zoneEdgeSwatch(color: string, glowOpacity: number): string {
  return (
    `<svg width="${GLYPH_PX}" height="${GLYPH_PX}" viewBox="0 0 16 16">` +
    `<rect x="4" y="4" width="8" height="8" rx="1" fill="none" stroke="${color}" ` +
    `stroke-width="2.6" stroke-opacity="${glowOpacity * 0.5}"/>` +
    `<rect x="2.5" y="2.5" width="11" height="11" rx="1.5" fill="none" stroke="${color}" ` +
    `stroke-opacity="0.9"/></svg>`
  )
}

const TYPES: TargetType[] = [
  'shahed', 'jet_drone', 'fpv', 'kab', 'missile', 'ballistic', 'unknown',
]

/** What the legend lists: colour = type, glyph = shape, and every row that has
 * an opposite carries it.
 *
 * There is no standing "destroyed" row any more. One grey struck-through glyph
 * had to stand for all five types, which is exactly the thing a legend is bad
 * at — now each type shows its own struck-through form, on demand.
 *
 * Homes are deliberately absent: the user picked their own marker and labelled
 * every contact's, so a legend entry explains nothing they don't already know
 * by looking. */
export function legendRows(): LegendRow[] {
  const rows: LegendRow[] = TYPES.map((ty) => ({
    id: ty,
    labelKey: `target.${ty}`,
    html: threatGlyphSvg(ty, { size: GLYPH_PX, color: TYPE_COLORS[ty] }),
    flipped: {
      labelKey: DOWN_LABEL_KEY[ty],
      // Grey, not the type colour: this is exactly how the map draws a closed
      // track, and a legend that recolours its subject teaches the wrong thing.
      html: threatGlyphSvg(ty, { size: GLYPH_PX, state: 'destroyed', color: MUTED_COLOR }),
    },
  }))
  rows.push({
    id: 'launcher',
    labelKey: 'legend.launcher',
    html: launcherGlyphSvg({ size: GLYPH_PX, color: TYPE_COLORS.ballistic }),
  })
  // The raion-alert layer is listed even while it is switched OFF. It used to
  // appear only once the layer was on, which made the legend useless for the
  // one thing it could have explained: what that siren button in the corner
  // would put on the map. Everything else here is a marker the operator has
  // already seen; this is the only row that can be news.
  rows.push({
    id: 'zone',
    labelKey: 'zones.alert',
    html: zoneEdgeSwatch(ZONE_STYLES.alert.color, ZONE_GLOW.opacity),
    flipped: {
      labelKey: 'zones.clear',
      html: zoneEdgeSwatch(ZONE_ALL_CLEAR.color, ZONE_ALL_CLEAR.opacity),
    },
  })
  return rows
}
