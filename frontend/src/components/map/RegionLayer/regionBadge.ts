/** What an oblast is to this reader, as one of three states. Ordered from
 * "mine" outward, which is also how loud each badge is. */
export type RegionBadgeState = 'followed' | 'inFeed' | 'out'

export function badgeStateOf(opts: { isHome: boolean; inFeed: boolean }): RegionBadgeState {
  if (opts.isHome) return 'followed'
  return opts.inFeed ? 'inFeed' : 'out'
}

const PHOSPHOR = '#22d3ee'

/** Per state: the glyph, its colours, and what a screen reader is told.
 *
 * The glyphs are stroke paths on a 24-box, drawn to match the lucide set the
 * rest of the app uses (star / eye / plus) without pulling React into a Leaflet
 * icon. Only the followed badge wears the accent — it is the one state the
 * reader cannot toggle, so it is a label rather than a switch. */
const BADGE: Record<
  RegionBadgeState,
  { path: string; color: string; ring: string; fill: string; label: string }
> = {
  followed: {
    path: 'M12 4.5l2.3 4.7 5.2.8-3.7 3.6.9 5.1-4.7-2.4-4.7 2.4.9-5.1-3.7-3.6 5.2-.8z',
    color: PHOSPHOR,
    ring: `${PHOSPHOR}88`,
    fill: 'rgba(8,20,25,0.88)',
    label: 'Основна область',
  },
  inFeed: {
    path: 'M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z M12 9.5a2.5 2.5 0 100 5 2.5 2.5 0 000-5z',
    color: '#cbd5e1',
    ring: '#cbd5e155',
    fill: 'rgba(8,15,20,0.85)',
    label: 'У стрічці подій',
  },
  out: {
    path: 'M12 6v12 M6 12h12',
    color: '#64748b',
    ring: '#64748b55',
    fill: 'rgba(8,15,20,0.7)',
    label: 'Поза стрічкою подій',
  },
}

/** The badge SVG for one state, as a string.
 *
 * Exists because the desktop affordance is a hover, and a finger has none: on a
 * phone the outlines just changed colour with nothing to say why, or that they
 * could be tapped at all. The badge is that missing half — it names the state
 * AND is the thing big enough to hit (the polygon fill is still tappable, but
 * an oblast at zoom 6 is a shape you have to aim at).
 *
 * A string rather than a React component because it ends up inside a Leaflet
 * divIcon, which owns its element. Kept in this module — free of any Leaflet
 * import — so the whole file stays testable in the DOM-free suite; RegionBadges
 * wraps it.
 */
export function badgeSvg(state: RegionBadgeState, size = 26): string {
  const b = BADGE[state]
  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">` +
    `<circle cx="12" cy="12" r="11" fill="${b.fill}" stroke="${b.ring}" stroke-width="1.2"/>` +
    `<path d="${b.path}" fill="none" stroke="${b.color}" stroke-width="1.8" ` +
    `stroke-linecap="round" stroke-linejoin="round"/>` +
    `</svg>`
  )
}

export const badgeLabel = (state: RegionBadgeState): string => BADGE[state].label
