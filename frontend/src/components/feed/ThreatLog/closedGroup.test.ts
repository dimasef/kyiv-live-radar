import { describe, expect, it } from 'vitest'

import type { FeedEntry } from '@/types'

import { isClosedGroup } from './timeline'

const AT = '2026-09-08T13:22:48Z'
const LATER = '2026-09-08T13:25:52Z'

/** One event of one message. `trackId` is what separates the two shapes that
 * look identical from the outside: several tracks, or several districts of one. */
function entry(trackId: number, closedAt: string | null = null): FeedEntry {
  return {
    event: {
      id: trackId * 10,
      threat_id: trackId,
      raw_text: 'Нивки / Шулявка / Лукʼянівка',
      event_time: AT,
      source_id: 13,
      source_message_id: 9756,
    },
    threat: { id: trackId, region: 'kyiv', target_type: 'jet_drone', closed_at: closedAt, events: [] },
  } as unknown as FeedEntry
}

describe('isClosedGroup', () => {
  it('is a stand-down when one message closed every track at its own instant', () => {
    const group = [entry(1, AT), entry(2, AT), entry(3, AT)]
    expect(isClosedGroup(group)).toBe(true)
  })

  it('is NOT closed when one message OPENED a track per district', () => {
    // Live 2026-09-08 16:22: «Нивки / Шулявка / Лукʼянівка» opened three tracks
    // and the feed announced three arriving jet drones as «Закрито цілей ×3».
    expect(isClosedGroup([entry(1), entry(2), entry(3)])).toBe(false)
  })

  it('does not turn a live card green when its tracks close later', () => {
    // The stand-down that closes them three minutes on belongs to ITS OWN
    // message's card, not to the sighting that first called them in.
    const group = [entry(1, LATER), entry(2, LATER), entry(3, LATER)]
    expect(isClosedGroup(group)).toBe(false)
  })

  it('needs a mix to be a group at all — one track is one sighting', () => {
    // A single sighting naming several districts is one track with several
    // events, and stays a normal card even once that track is closed.
    expect(isClosedGroup([entry(1, AT), entry(1, AT)])).toBe(false)
    expect(isClosedGroup([entry(1)])).toBe(false)
  })

  it('is not closed while any one of the tracks is still open', () => {
    expect(isClosedGroup([entry(1, AT), entry(2, null)])).toBe(false)
  })

  it('compares instants, not the strings two schemas happened to render', () => {
    expect(isClosedGroup([entry(1, '2026-09-08T13:22:48+00:00'), entry(2, AT)])).toBe(true)
  })

  it('refuses to call a group closed on a stamp it cannot read', () => {
    // NaN fails the comparison, which is the safe direction: a plain sighting
    // card is never a false claim, a green "closed" one is.
    expect(isClosedGroup([entry(1, 'not a date'), entry(2, AT)])).toBe(false)
  })
})
