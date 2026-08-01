// The origin counts as "on screen" only once it's this many px inside the edge —
// right at the border a wedge still reads better than a half-clipped marker.
export const VIEW_MARGIN_PX = 56

/** Where a wedge sits on the container edge, in %, for a compass bearing.
 * Resolution-independent: intersect the ray from centre with the unit box. */
export function edgePercent(bearingDeg: number): { left: number; top: number } {
  const rad = (bearingDeg * Math.PI) / 180
  const dx = Math.sin(rad) // east = +x
  const dy = -Math.cos(rad) // north = -y (screen y grows downward)
  const tx = dx !== 0 ? 0.5 / Math.abs(dx) : Infinity
  const ty = dy !== 0 ? 0.5 / Math.abs(dy) : Infinity
  const t = Math.min(tx, ty) * 0.86 // inset so the wedge isn't clipped
  return { left: (0.5 + t * dx) * 100, top: (0.5 + t * dy) * 100 }
}

export function isWellInsideView(
  x: number,
  y: number,
  size: { x: number; y: number },
): boolean {
  return (
    x >= VIEW_MARGIN_PX &&
    x <= size.x - VIEW_MARGIN_PX &&
    y >= VIEW_MARGIN_PX &&
    y <= size.y - VIEW_MARGIN_PX
  )
}
