export interface PixelPoint {
  id: string
  x: number
  y: number
}

/** Screen-pixel offset to apply to a marker so it stops sitting on top of its
 * neighbours. Keyed by point id; ids absent from the map need no offset. */
export type Offsets = Map<string, [number, number]>

/** Fan out markers that land within `minGap` pixels of each other.
 *
 * Two homes in the same building project to the same pixel, and the later
 * marker simply hides the earlier one — most painfully when a contact's icon
 * covers YOUR home, the one thing on the map that is always supposed to be
 * findable. Rather than move anyone to a false location, this only shifts how
 * the icons are DRAWN (the marker still belongs to its true coordinates; see
 * FriendLayer, which applies the offset through iconAnchor).
 *
 * `anchorId` — a point that must not move, so the whole cluster arranges itself
 * around it. That's the user's own home: it anchors the danger circle, and a
 * house drawn off its circle's centre would read as a bug.
 *
 * Clustering is single-link and O(n²), which is the right trade at this scale:
 * a contact list is a handful of people, and anything cleverer would cost more
 * to read than it saves to run.
 */
export function spreadOverlapping(
  points: PixelPoint[],
  { minGap = 26, anchorId }: { minGap?: number; anchorId?: string } = {},
): Offsets {
  const offsets: Offsets = new Map()
  if (points.length < 2) return offsets

  // Stable input order → stable output: without it a re-render could reshuffle
  // which contact sits where, and the icons would swap places under the cursor.
  const sorted = [...points].sort((a, b) => a.id.localeCompare(b.id))
  const clusterOf = new Map<string, number>()
  const clusters: PixelPoint[][] = []

  for (const p of sorted) {
    const near = clusters.findIndex((cluster) =>
      cluster.some((q) => Math.hypot(q.x - p.x, q.y - p.y) < minGap),
    )
    if (near === -1) {
      clusterOf.set(p.id, clusters.length)
      clusters.push([p])
    } else {
      clusterOf.set(p.id, near)
      clusters[near].push(p)
    }
  }

  for (const cluster of clusters) {
    if (cluster.length < 2) continue
    // Put the anchor first so it takes the centre slot (offset 0,0).
    const ordered =
      anchorId != null && cluster.some((p) => p.id === anchorId)
        ? [
            cluster.find((p) => p.id === anchorId)!,
            ...cluster.filter((p) => p.id !== anchorId),
          ]
        : cluster
    const [centre, ...rest] = ordered
    offsets.set(centre.id, [0, 0])
    const k = rest.length
    // Big enough that ring members clear the centre (minGap) AND each other —
    // for k markers on a circle the chord between neighbours is 2·r·sin(π/k).
    const radius = k === 1 ? minGap : Math.max(minGap, minGap / (2 * Math.sin(Math.PI / k)))
    rest.forEach((p, i) => {
      // Start at 12 o'clock and go clockwise; the first one sits directly above
      // the centre, which reads as "these two belong together".
      const angle = (2 * Math.PI * i) / k - Math.PI / 2
      // Offsets are measured from each marker's OWN position, so aim at an
      // absolute slot on the ring rather than nudging by the ring vector —
      // cluster members start a few pixels apart, and nudging would carry that
      // scatter onto the ring and let two of them close back in on each other.
      const targetX = centre.x + radius * Math.cos(angle)
      const targetY = centre.y + radius * Math.sin(angle)
      offsets.set(p.id, [Math.round(targetX - p.x), Math.round(targetY - p.y)])
    })
  }

  return offsets
}
