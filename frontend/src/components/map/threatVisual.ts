import { threatState } from '@/threatDisplay'
import { threatColor } from '@/theme'
import { DIRECTIONAL, DOT_UNTIL_MOVING } from '@/threatIcons'
import type { Threat } from '@/types'

import type { Pt } from '@/lib/geo'

import { KYIV_PT } from './constants'
import { hasMovement, headingOf, inboundHeading, trackPoints } from './track'

export interface ThreatVisual {
  pts: Pt[]
  color: string
  /** Did the target actually travel, i.e. should the map draw a vector at all? */
  moved: boolean
  /** Where the glyph points, real or presumed inbound; null = an honest dot. */
  heading: number | null
  /** Glyph shape state — burst, struck through, pointing along the heading. */
  state: ReturnType<typeof threatState>
}

/** Everything the map needs to DRAW one track, derived from the track alone.
 *
 * Pure and hook-free, so the rules that decide whether a target gets a vector
 * (and which way its glyph points) can be read — and tested — without a Leaflet
 * map or a React tree around them. */
export function threatVisual(threat: Threat): ThreatVisual {
  const pts = trackPoints(threat)
  const type = threat.target_type

  // Only a track that actually moved gets a heading/vector — a single
  // multi-district message is an enumeration, not a trajectory, UNLESS it
  // stated a path between the places (see hasMovement).
  // An impact is a POINT strike, never a trajectory: it must NEVER draw a
  // connecting vector even when re-reports give it several timestamps (a
  // ballistic can't "move" between districts) — so kind='impact' is excluded.
  const moved = threat.kind !== 'impact' && hasMovement(threat)
  const realHeading = moved ? headingOf(threat) : null

  // A drone sighted as a single point still flies toward Kyiv — aim its glyph
  // inbound rather than a meaningless due-north. Missiles stay a fix dot until
  // they truly move, so exclude DOT_UNTIL_MOVING types.
  const last = pts.length > 0 ? pts[pts.length - 1] : null
  const presumedHeading =
    realHeading == null && last != null && DIRECTIONAL[type] && !DOT_UNTIL_MOVING[type]
      ? inboundHeading(last, KYIV_PT, threat.id)
      : null
  const heading = realHeading ?? presumedHeading

  return {
    pts,
    color: threatColor(threat),
    moved,
    heading,
    // Head-marker state: influences SHAPE. A hit bursts; a shot-down/lost track
    // is struck through; a moving track points along its heading. A cruise
    // missile with no heading yet is an honest dot (DOT_UNTIL_MOVING); drones
    // and ballistic/unknown show their glyph from the first sighting (a drone
    // points up until it gains a course, then rotates along the vector).
    state: threatState(threat, { heading, directional: DOT_UNTIL_MOVING[type] }),
  }
}
