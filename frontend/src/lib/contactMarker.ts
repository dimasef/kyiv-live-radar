import { FRIEND_HOME_COLOR } from '@/theme'

/** Per-contact map-marker appearance the user can pick — a local labelling aid
 * (see friendsSlice.contactStyles), NOT shared with the contact. The same
 * palette + shapes drive the map divIcon (FriendLayer) and the settings picker
 * (ContactsSection), so a chosen swatch always matches the marker on the map. */
export interface ContactStyle {
  color: string
  icon: string
}

/** Distinct, pleasant hues for labelling contacts. First entry is the default
 * (kept in sync with the map's FRIEND_HOME_COLOR). */
export const CONTACT_COLORS: string[] = [
  FRIEND_HOME_COLOR, // pink
  '#c084fc', // violet
  '#60a5fa', // blue
  '#2dd4bf', // teal
  '#34d399', // emerald
  '#fbbf24', // amber
  '#fb7185', // rose
  '#f8fafc', // white
]

// Each icon is the INNER markup of a 24×24 SVG; the wrapper supplies fill/stroke
// so one shape renders in any colour. `person` is the default silhouette.
const ICON_INNER: Record<string, string> = {
  person:
    '<circle cx="12" cy="7" r="4"/><path d="M4 21 C4 15 8 13 12 13 C16 13 20 15 20 21 Z"/>',
  home: '<path d="M12 3 L21 11 L18 11 L18 20 L14 20 L14 14 L10 14 L10 20 L6 20 L6 11 L3 11 Z"/>',
  heart: '<path d="M12 21 C12 21 3 14.5 3 8.5 A4.8 4.8 0 0 1 12 6 A4.8 4.8 0 0 1 21 8.5 C21 14.5 12 21 12 21 Z"/>',
  star: '<path d="M12 2 L14.7 8.6 L21.6 9 L16.3 13.5 L18 20.2 L12 16.4 L6 20.2 L7.7 13.5 L2.4 9 L9.3 8.6 Z"/>',
  pin: '<path d="M12 2 C8.1 2 5 5.1 5 9 C5 14 12 22 12 22 C12 22 19 14 19 9 C19 5.1 15.9 2 12 2 Z"/>',
  diamond: '<path d="M12 2 L22 12 L12 22 L2 12 Z"/>',
}

export const CONTACT_ICONS: string[] = Object.keys(ICON_INNER)

export const DEFAULT_CONTACT_COLOR = FRIEND_HOME_COLOR
export const DEFAULT_CONTACT_ICON = 'person'

/** Full SVG markup for a marker in the given icon+colour at `size` px — shared
 * by the Leaflet divIcon and the picker glyph. */
export function contactMarkerSvg(icon: string, color: string, size: number): string {
  const inner = ICON_INNER[icon] ?? ICON_INNER[DEFAULT_CONTACT_ICON]
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="filter:drop-shadow(0 0 5px ${color})"><g fill="${color}" stroke="#0b0f14" stroke-width="1" stroke-linejoin="round">${inner}</g></svg>`
}

/** A contact's chosen style, falling back to the default marker. */
export function contactStyleOf(style: ContactStyle | undefined): ContactStyle {
  return {
    color: style?.color ?? DEFAULT_CONTACT_COLOR,
    icon: style?.icon ?? DEFAULT_CONTACT_ICON,
  }
}
