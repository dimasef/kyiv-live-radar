import L from 'leaflet'

import { AFTERMATH_COLOR } from '@/theme'
import type { AftermathCategory } from '@/types'

/** Marker glyphs for the consequence layer's other half — what a strike DID to
 * a place, as opposed to a confirmed hit.
 *
 * One colour for all four, shape carrying the meaning. That is the same rule
 * `threatIcons` follows for an impact ("the burst SHAPE marks the hit"), and it
 * is what keeps the layer readable: a reader scanning it wants to see WHERE
 * something happened first and what kind second, and four hues competing with
 * the target palette would invert that.
 *
 * Stroke-only, no fill, no pulse. A target pulses because it is still in the
 * air; a burnt-out building is the opposite of that, and animating it would say
 * something untrue.
 */

const GLYPHS: Record<AftermathCategory, (c: string) => string> = {
  // A flame outline — the one shape nobody has to be taught.
  fire: (c) =>
    `<path d="M8 2.2c1.9 2.6 3.7 3.6 2.9 6.2a3.1 3.1 0 1 1-5.8 0C4.3 5.8 6.1 4.8 8 2.2Z" ` +
    `fill="none" stroke="${c}" stroke-width="1.4" stroke-linejoin="round"/>`,
  // A building with a break through it. Not rubble (unreadable at 16px): the
  // crack is the whole message.
  damage: (c) =>
    `<rect x="3.5" y="4" width="9" height="8.5" fill="none" stroke="${c}" ` +
    `stroke-width="1.3"/>` +
    `<path d="M8 4 6.6 7.4 9 8.6 7.4 12.5" fill="none" stroke="${c}" ` +
    `stroke-width="1.3" stroke-linejoin="round"/>`,
  // A ring — the life-buoy read, for work still going on with people in it.
  rescue: (c) =>
    `<circle cx="8" cy="8" r="5" fill="none" stroke="${c}" stroke-width="1.4"/>` +
    `<circle cx="8" cy="8" r="1.8" fill="none" stroke="${c}" stroke-width="1.2"/>`,
  // A cross. The medical read, and the only glyph here that is about people
  // rather than property — hence the plainest shape in the set.
  casualties: (c) =>
    `<path d="M8 3.2v9.6M3.2 8h9.6" stroke="${c}" stroke-width="1.6" ` +
    `stroke-linecap="round"/>`,
}

export function aftermathGlyphSvg(
  category: AftermathCategory,
  { size = 16, color = AFTERMATH_COLOR }: { size?: number; color?: string } = {},
): string {
  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 16 16" ` +
    `xmlns="http://www.w3.org/2000/svg">${GLYPHS[category](color)}</svg>`
  )
}

/** A leaflet icon for one report. `category` is the report's LAST category —
 * the list arrives ordered least → most consequential from the server, so the
 * marker shows the worst thing that happened there without the client
 * re-deriving an order the backend owns (domain/aftermath.py::_SEVERITY).
 *
 * `extra` is the count of the other categories, shown as the same «+N» chip the
 * target markers use for a group size: «пожежа +2» says at a glance that this
 * raion's report is not only a fire, and the popup lists all of them. */
export function aftermathDivIcon(
  category: AftermathCategory,
  { size = 22, extra = 0 }: { size?: number; extra?: number } = {},
): L.DivIcon {
  const badge =
    extra > 0 ? `<span class="threat-count">+${extra}</span>` : ''
  return L.divIcon({
    html: aftermathGlyphSvg(category, { size }) + badge,
    className: 'threat-icon',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}
