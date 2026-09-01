import { describe, expect, it } from 'vitest'

import type { Alert } from '@/types'

import { alertCoversMe, primaryAlert } from './coverage'

const alert = (over: Partial<Alert>): Alert =>
  ({
    id: 1,
    region: 'kyiv',
    scope: 'city',
    zone_id: null,
    alert_type: 'air_raid',
    started_at: '2026-09-01T20:00:00Z',
    ended_at: null,
    provider: 'telegram',
    closed_reason: null,
    ...over,
  }) as Alert

const KYIV_CITY = { zoneId: 'kyiv-city', region: 'kyiv' as const }
const BROVARY = { zoneId: 'kyiv-obl-brovarskyi', region: 'kyiv' as const }
const NO_HOME = { zoneId: null, region: 'kyiv' as const }

describe('alertCoversMe', () => {
  it('does not hand a Kyiv city siren to someone in the oblast', () => {
    // The bug this whole layer exists for: region `kyiv` covers м. Київ AND the
    // oblast around it, so a Brovary reader was shown the capital's alert as
    // their own — and never saw their own raion's.
    expect(alertCoversMe(alert({ scope: 'city' }), BROVARY)).toBe(false)
  })

  it('gives the Kyiv city siren to someone in the city', () => {
    expect(alertCoversMe(alert({ scope: 'city' }), KYIV_CITY)).toBe(true)
  })

  it('gives a raion alert only to that raion', () => {
    const brovary = alert({ scope: 'raion', zone_id: 'kyiv-obl-brovarskyi' })
    expect(alertCoversMe(brovary, BROVARY)).toBe(true)
    expect(alertCoversMe(brovary, KYIV_CITY)).toBe(false)
    expect(alertCoversMe(brovary, { zoneId: 'kyiv-obl-buchanskyi', region: 'kyiv' })).toBe(false)
  })

  it('gives an oblast-wide announcement to everyone in the region', () => {
    const oblast = alert({ scope: 'oblast' })
    expect(alertCoversMe(oblast, BROVARY)).toBe(true)
    expect(alertCoversMe(oblast, KYIV_CITY)).toBe(true)
  })

  it('never crosses regions', () => {
    expect(alertCoversMe(alert({ region: 'sumy', scope: 'oblast' }), BROVARY)).toBe(false)
    expect(
      alertCoversMe(
        alert({ region: 'sumy', scope: 'raion', zone_id: 'sumy-obl-sumskyi' }),
        { zoneId: 'sumy-obl-sumskyi', region: 'sumy' },
      ),
    ).toBe(true)
  })

  it('falls back to the oblast granularity when there is no home', () => {
    // Unchanged from before this feature: an official city/oblast alert still
    // reaches a reader who has not marked a home…
    expect(alertCoversMe(alert({ scope: 'city' }), NO_HOME)).toBe(true)
    // …but a raion siren 40 km away does not become their banner.
    expect(
      alertCoversMe(alert({ scope: 'raion', zone_id: 'kyiv-obl-buchanskyi' }), NO_HOME),
    ).toBe(false)
  })

  it('shows anything while the followed region is still unknown', () => {
    // First paint, before the catalogue lands and with no explicit choice —
    // failing towards showing an alert is the only safe direction here.
    expect(alertCoversMe(alert({ region: 'sumy' }), { zoneId: null, region: null })).toBe(true)
  })
})

describe('primaryAlert', () => {
  it('ignores ended alerts', () => {
    expect(primaryAlert([alert({ ended_at: '2026-09-01T21:00:00Z' })])).toBeNull()
  })

  it('prefers the official announcement over a raion one', () => {
    const raion = alert({ id: 2, scope: 'raion', zone_id: 'kyiv-obl-brovarskyi' })
    const official = alert({ id: 3, scope: 'city' })
    expect(primaryAlert([raion, official])?.id).toBe(3)
  })

  it('falls back to the raion alert when that is all there is', () => {
    const raion = alert({ id: 2, scope: 'raion', zone_id: 'kyiv-obl-brovarskyi' })
    expect(primaryAlert([raion])?.id).toBe(2)
  })
})
