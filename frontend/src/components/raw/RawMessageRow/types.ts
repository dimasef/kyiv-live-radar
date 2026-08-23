import type { Threat } from '@/types'

/** Tell the list a sighting is gone, so the row stops advertising it. */
export type DropEvent = (messageId: number, eventId: number) => void

/** Tell the list a sighting now belongs to a different track. */
export type MoveEvent = (eventId: number, threatId: number) => void

/** Tell the list a track's server state changed, so every chip of that track
 * across every loaded row redraws — one track's sightings are scattered over as
 * many messages as reported it. */
export type ApplyTrack = (track: Threat) => void
