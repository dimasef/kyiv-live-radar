import { FRIEND_HOME_COLOR, HOME_COLOR } from '@/theme'

import { MARKER_ICONS } from './markerIcons'

/** How one home is drawn on the map. Two things share this shape and its
 * picker: a CONTACT's marker (friendsSlice.contactStyles) and the user's OWN
 * home marker (homeSlice.homeStyle). Both are private to the viewer — a contact
 * is never told how you labelled them, and your own marker is yours alone.
 *
 * The same palette + shapes drive the Leaflet divIcons and the picker, so a
 * chosen swatch always matches the marker on the map. */
export interface ContactStyle {
  color: string
  icon: string
  /** Whether the marker carries its coloured halo. On by default — it's what
   * makes a marker read as lit-up rather than printed — but a busy corner of
   * the map is calmer with it off. */
  glow: boolean
}

/** Distinct, pleasant hues for labelling homes. First entry is the default
 * contact colour (kept in sync with the map's FRIEND_HOME_COLOR). */
export const CONTACT_COLORS: string[] = [
  FRIEND_HOME_COLOR, // pink
  '#c084fc', // violet
  '#60a5fa', // blue
  '#2dd4bf', // teal
  '#34d399', // emerald
  '#fbbf24', // amber
  '#f87171', // red
  '#ffffff', // white
]

/** The same palette for the user's OWN home, plus the cyan it defaults to —
 * otherwise the one colour a user is most likely to want back is the one they
 * can't pick. */
export const HOME_COLORS: string[] = [HOME_COLOR, ...CONTACT_COLORS]

export const CONTACT_ICONS = MARKER_ICONS

const ICON_BODY: Record<string, string> = Object.fromEntries(
  MARKER_ICONS.map((i) => [i.id, i.body]),
)

export const DEFAULT_CONTACT_COLOR = FRIEND_HOME_COLOR
export const DEFAULT_CONTACT_ICON = 'person'

/** Left alone, the user's own home keeps the look it had before it was
 * choosable: the cyan house. This colour only ever shows while nothing is
 * threatening the home — MapView paints the danger colours over it. */
export const DEFAULT_HOME_COLOR = HOME_COLOR
export const DEFAULT_HOME_ICON = 'home'

/** Full SVG markup for a marker in the given icon+colour at `size` px — shared
 * by the Leaflet divIcons and the picker glyph.
 *
 * The shapes paint themselves with `currentColor`, so colour is set once on the
 * wrapper. The tight dark drop-shadow stays even with the halo off: it is what
 * keeps a pale marker legible over a pale patch of map, and the detailed shapes
 * can't carry the 1px outline the six original ones had without turning to mud
 * at 22 px. */
export function contactMarkerSvg(
  icon: string,
  color: string,
  size: number,
  glow = true,
): string {
  const body = ICON_BODY[icon] ?? ICON_BODY[DEFAULT_CONTACT_ICON]
  const halo = glow ? `drop-shadow(0 0 5px ${color}) ` : ''
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="color:${color};filter:${halo}drop-shadow(0 0 1px #0b0f14)">${body}</svg>`
}

/** A contact's chosen style, falling back to the default marker. A style saved
 * before the halo was choosable has no `glow` — it keeps the halo it had. */
export function contactStyleOf(style: Partial<ContactStyle> | undefined): ContactStyle {
  return {
    color: style?.color ?? DEFAULT_CONTACT_COLOR,
    icon: style?.icon ?? DEFAULT_CONTACT_ICON,
    glow: style?.glow ?? true,
  }
}

/** The user's own home style, falling back to the classic cyan house. */
export function homeStyleOf(style: Partial<ContactStyle> | null | undefined): ContactStyle {
  return {
    color: style?.color ?? DEFAULT_HOME_COLOR,
    icon: style?.icon ?? DEFAULT_HOME_ICON,
    glow: style?.glow ?? true,
  }
}
