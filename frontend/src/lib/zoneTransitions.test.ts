import { describe, expect, it } from 'vitest'

import type { AlertZone } from '@/types'

import { allClearedZoneIds } from './zoneTransitions'

const zone = (over: Partial<AlertZone> = {}): AlertZone => ({
  zone_id: 'kyiv-obl-vyshhorodskyi',
  name_uk: 'Вишгородський район',
  oblast: 'Київська область',
  alert: false,
  changed_at: null,
  stale: false,
  ...over,
})

describe('allClearedZoneIds', () => {
  it('reports a siren that was called off while we were watching', () => {
    const held = { a: zone({ zone_id: 'a', alert: true }) }
    expect(allClearedZoneIds(held, [zone({ zone_id: 'a', alert: false })])).toEqual(['a'])
  })

  it('stays silent for a zone seen for the first time', () => {
    // Boot hydration: every raion arrives at once, most of them quiet. Flashing
    // those would announce all-clears that may have ended hours ago.
    expect(allClearedZoneIds({}, [zone({ zone_id: 'a', alert: false })])).toEqual([])
  })

  it('stays silent when the provider merely came back', () => {
    // We stopped knowing while it was stale — "clear" is news about the
    // connection, not about the siren.
    const held = { a: zone({ zone_id: 'a', alert: true, stale: true }) }
    expect(allClearedZoneIds(held, [zone({ zone_id: 'a', alert: false })])).toEqual([])
  })

  it('stays silent when the provider goes unreachable under an active siren', () => {
    const held = { a: zone({ zone_id: 'a', alert: true }) }
    expect(allClearedZoneIds(held, [zone({ zone_id: 'a', alert: false, stale: true })])).toEqual([])
  })

  it('ignores zones that did not change and zones that lit up', () => {
    const held = {
      a: zone({ zone_id: 'a', alert: true }),
      b: zone({ zone_id: 'b', alert: false }),
      c: zone({ zone_id: 'c', alert: false }),
    }
    const incoming = [
      zone({ zone_id: 'a', alert: false }),
      zone({ zone_id: 'b', alert: false }),
      zone({ zone_id: 'c', alert: true }),
    ]
    expect(allClearedZoneIds(held, incoming)).toEqual(['a'])
  })
})
