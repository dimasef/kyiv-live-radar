import type { WSMessage } from '@/types'

/** Where this client stands in the server's frame stream — what GET /sync is
 * asked to replay from after a reconnect. */
export interface StreamPosition {
  epoch: number
  seq: number
}

/** 'ping' and 'online' are stamped with the server's CURRENT position but are
 * not part of the replayable stream (see realtime/ws.py). Adopting theirs
 * would carry the client past every frame it had not actually applied: the
 * 'online' frame that opens every reconnect used to do exactly that, and the
 * replay that followed it then skipped everything the client had missed —
 * a track the sweeper closed during a short absence stayed «фіксується» on
 * the map for an hour. Only a data frame moves the position; an unsequenced
 * one seeds it just once, right after a boot hydrate, so the first reconnect
 * can still ask for a delta instead of re-fetching everything. */
const UNSEQUENCED: ReadonlySet<WSMessage['type']> = new Set(['ping', 'online'])

export function advance(position: StreamPosition | null, frame: WSMessage): StreamPosition | null {
  if (frame.epoch == null || frame.seq == null) return position
  if (position != null && UNSEQUENCED.has(frame.type)) return position
  return { epoch: frame.epoch, seq: frame.seq }
}

/** Whether a replayed frame is one the client has already applied — a live
 * frame on the fresh socket may have overtaken the replay, and re-applying an
 * older one would roll its track back. */
export function alreadyApplied(position: StreamPosition | null, frame: WSMessage): boolean {
  if (position == null || frame.seq == null) return false
  return frame.epoch === position.epoch && frame.seq <= position.seq
}
