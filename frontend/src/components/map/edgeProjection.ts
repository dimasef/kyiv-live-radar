// The origin counts as "on screen" only once it's this many px inside the edge —
// right at the border an edge marker still reads better than a half-clipped one.
export const VIEW_MARGIN_PX = 56

/** Px kept clear on each side of the map container — the alert banner at the
 * top, the mobile feed sheet at the bottom, and so on. */
export interface EdgeInsets {
  top: number
  right: number
  bottom: number
  left: number
}

/** The strip of map an edge marker may sit in. The container runs edge to edge
 * and UNDER its overlays, so the sides to stay clear of are spelled out here:
 * the alert banner up top, and on mobile the collapsed feed sheet (3.4rem)
 * plus the attribution line at the bottom.
 *
 * The wider right inset on desktop is the feed's collapse handle
 * (chrome/FeedToggle), which is 20 px of chip at exactly the mid-height an edge
 * marker likes. It is there in both states — expanded, it rides the seam. */
export function overlayInsets(): EdgeInsets {
  const desktop = window.matchMedia('(min-width: 1024px)').matches
  return { top: 64, right: desktop ? 26 : 12, bottom: desktop ? 44 : 76, left: 12 }
}

/** The origin counts as visible only once it is clear of those overlays AND a
 * marker's width inside the container edge — right at the border an edge
 * marker reads better than a half-clipped one. */
export function visibleInsets(i: EdgeInsets): EdgeInsets {
  return {
    top: Math.max(i.top, VIEW_MARGIN_PX),
    right: Math.max(i.right, VIEW_MARGIN_PX),
    bottom: Math.max(i.bottom, VIEW_MARGIN_PX),
    left: Math.max(i.left, VIEW_MARGIN_PX),
  }
}

/** The same box grown OUTWARD by `px` on every side.
 *
 * Insets go negative once the box passes the container edge, which is exactly
 * what "this far off screen" has to mean — `isInsideBox` compares plain
 * numbers, so it reads a negative inset as intended.
 *
 * For a hysteresis margin: something has to clear the visible area by a real
 * distance before an edge marker is worth showing, otherwise the marker flickers
 * in and out while the map is dragged along that boundary. */
export function outsetInsets(i: EdgeInsets, px: number): EdgeInsets {
  return { top: i.top - px, right: i.right - px, bottom: i.bottom - px, left: i.left - px }
}

/** Top-left px of an edge marker of the given size, for a compass bearing,
 * projected onto the box left after `insets` and kept fully inside it.
 *
 * Unlike `edgePercent`, which centres a small wedge on the container edge, this
 * takes the marker's own footprint into account: a wide pill centred on the
 * edge is half-clipped on a phone, and the bottom of the map lies under the
 * feed sheet, which no percentage of the container knows about. */
export function edgeMarkerPosition(
  bearingDeg: number,
  size: { x: number; y: number },
  insets: EdgeInsets,
  marker: { width: number; height: number },
): { left: number; top: number } {
  const left = insets.left
  const top = insets.top
  const right = Math.max(size.x - insets.right, left)
  const bottom = Math.max(size.y - insets.bottom, top)
  const halfW = (right - left) / 2
  const halfH = (bottom - top) / 2

  const rad = (bearingDeg * Math.PI) / 180
  const dx = Math.sin(rad) // east = +x
  const dy = -Math.cos(rad) // north = -y (screen y grows downward)
  const tx = dx !== 0 ? halfW / Math.abs(dx) : Infinity
  const ty = dy !== 0 ? halfH / Math.abs(dy) : Infinity
  const t = Math.min(tx, ty)

  // Centre on the boundary hit, then slide back inside — that keeps the marker
  // flush with the edge it points past AND clear of the two corners it would
  // otherwise spill over.
  return {
    left: clamp((left + right) / 2 + t * dx - marker.width / 2, left, right - marker.width),
    top: clamp((top + bottom) / 2 + t * dy - marker.height / 2, top, bottom - marker.height),
  }
}

/** Clamp that survives an empty range (a container narrower than the marker):
 * the low bound wins, so the marker stays anchored instead of jumping. */
function clamp(v: number, lo: number, hi: number): number {
  return hi <= lo ? lo : Math.min(Math.max(v, lo), hi)
}

/** Is the point inside the box left after `insets` — i.e. visible, and not
 * tucked under whatever overlays the map there? */
export function isInsideBox(
  x: number,
  y: number,
  size: { x: number; y: number },
  insets: EdgeInsets,
): boolean {
  return (
    x >= insets.left &&
    x <= size.x - insets.right &&
    y >= insets.top &&
    y <= size.y - insets.bottom
  )
}

/** Compass bearing (degrees, 0 = up) of a screen-space delta. Screen y grows
 * downward, so north is -y. Used to point at something whose place on screen is
 * already known — unlike a geographic bearing, this stays true under whatever
 * projection the map is drawn in. */
export function screenBearing(dx: number, dy: number): number {
  return (Math.atan2(dx, -dy) * 180) / Math.PI
}
