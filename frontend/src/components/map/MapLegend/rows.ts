import { ZONE_ALL_CLEAR, ZONE_GLOW, ZONE_STYLES } from '@/components/map/constants'
import { MUTED_COLOR, TYPE_COLORS } from '@/theme'
import { impactGlyphSvg, launcherGlyphSvg, threatGlyphSvg } from '@/threatIcons'
import { DOWN_LABEL_KEY } from '@/threatLabels'
import type { TargetType } from '@/types'

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
export function legendRows({ impacts = false }: { impacts?: boolean } = {}): LegendRow[] {
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
    id: 'echo',
    labelKey: 'legend.echo',
    html:
      `<svg width="${GLYPH_PX}" height="${GLYPH_PX}" viewBox="0 0 16 16">` +
      `<circle cx="8" cy="8" r="4" fill="none" stroke="${TYPE_COLORS.shahed}" ` +
      `stroke-width="1.4" stroke-dasharray="2 2" stroke-opacity="0.85"/></svg>`,
  })
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
  // Same rule as the raion-alert row below: listed while the layer is off,
  // so the flame button in the corner is explained before it is pressed. Only
  // for the accounts that have that button at all — the legend is what every
  // reader sees, and the layer's existence is withheld from the rest.
  // One row for both halves: on the map they are the same ring in the same
  // colour, and a legend that listed it twice would be explaining a difference
  // the reader cannot see.
  if (impacts) {
    rows.push({
      id: 'impact',
      labelKey: 'legend.impacts',
      html: impactGlyphSvg({ size: GLYPH_PX }),
    })
  }
  // Two rows, because the layer now paints two levels and they are the one
  // thing about it a reader has to be told rather than shown: amber and red
  // side by side on the map mean nothing until the legend names them. Named
  // by what they MEAN (drones / missiles), not by their colour — the swatch
  // already shows the colour. The all-clear flash stays on the red row rather
  // than getting a third — it is the same «відбій» whichever level preceded it.
  rows.push({
    id: 'zone-yellow',
    labelKey: 'legend.zoneYellow',
    html: zoneEdgeSwatch(ZONE_STYLES.yellow.color, ZONE_GLOW.yellow.opacity),
  })
  rows.push({
    id: 'zone',
    labelKey: 'legend.zoneRed',
    html: zoneEdgeSwatch(ZONE_STYLES.red.color, ZONE_GLOW.red.opacity),
    flipped: {
      labelKey: 'zones.clear',
      html: zoneEdgeSwatch(ZONE_ALL_CLEAR.color, ZONE_ALL_CLEAR.opacity),
    },
  })
  return rows
}
