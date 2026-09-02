import { describe, expect, it } from 'vitest'

import type { Home } from '@/store/homeSlice'
import type { Threat, ThreatEvent } from '@/types'

import { homeDistanceOf, sightingDistanceOf } from './homeDistance'

const HOME: Home = { lat: 50.45, lon: 30.52, radiusKm: 3, origin: 'manual' }

/** One sighting. `at` is a minute offset — only the ordering matters. */
function event(lat: number | null, lon: number | null, at: number): ThreatEvent {
  return {
    id: at,
    threat_id: 1,
    district_id: 1,
    event_time: `2026-08-08T22:${String(at).padStart(2, '0')}:00`,
    lat,
    lon,
    raw_text: '',
    confidence: 0.8,
    decision_source: 'rule',
  }
}

function threat(
  events: ThreatEvent[],
  scope: Threat['scope'] = 'district',
  closed?: Partial<Pick<Threat, 'closed_at' | 'closed_reason' | 'status' | 'kind'>>,
): Threat {
  return {
    id: 1,
    target_type: 'shahed',
    status: 'tracking',
    kind: 'track',
    scope,
    region: 'kyiv',
    target_count: 1,
    target_count_locked: false,
    confidence: 0.8,
    movement_stated: false,
    corroboration_count: 1,
    has_conflict: false,
    created_at: '2026-08-08T22:00:00',
    events,
    ...closed,
  }
}

/** ~11 km due north of home, ~22 km due north, etc. */
const northOfHome = (km: number) => ({ lat: HOME.lat + km / 111.19, lon: HOME.lon })

describe('homeDistanceOf', () => {
  it('measures from the newest sighting, not the first one', () => {
    const far = northOfHome(20)
    const near = northOfHome(5)
    const d = homeDistanceOf(threat([event(far.lat, far.lon, 1), event(near.lat, near.lon, 9)]), HOME)
    expect(d?.km).toBeCloseTo(5, 1)
  })

  it('takes the NEAREST of several districts named in one message', () => {
    // "по Дарницькому та Дніпровському" — same timestamp, no trajectory; the
    // number must not understate how close the target got.
    const a = northOfHome(12)
    const b = northOfHome(4)
    const d = homeDistanceOf(threat([event(a.lat, a.lon, 5), event(b.lat, b.lon, 5)]), HOME)
    expect(d?.km).toBeCloseTo(4, 1)
    expect(d?.trend).toBeNull() // an enumeration is not movement
  })

  it('points due north when the target is north of home', () => {
    const p = northOfHome(8)
    expect(homeDistanceOf(threat([event(p.lat, p.lon, 1)]), HOME)?.bearingFromHome).toBeCloseTo(0, 3)
  })

  it('reads a track moving toward home as closing, and away as receding', () => {
    const far = northOfHome(20)
    const near = northOfHome(6)
    expect(
      homeDistanceOf(threat([event(far.lat, far.lon, 1), event(near.lat, near.lon, 5)]), HOME)?.trend,
    ).toBe('closing')
    expect(
      homeDistanceOf(threat([event(near.lat, near.lon, 1), event(far.lat, far.lon, 5)]), HOME)?.trend,
    ).toBe('receding')
  })

  it('calls a sub-km shift no trend at all — centroids cannot resolve it', () => {
    const a = northOfHome(9)
    const b = northOfHome(8.5)
    expect(homeDistanceOf(threat([event(a.lat, a.lon, 1), event(b.lat, b.lon, 5)]), HOME)?.trend).toBeNull()
  })

  it('flags a target inside the home zone plus its buffer', () => {
    const inside = northOfHome(4) // radius 3 + buffer 2
    expect(homeDistanceOf(threat([event(inside.lat, inside.lon, 1)]), HOME)?.nearHome).toBe(true)
    const outside = northOfHome(9)
    expect(homeDistanceOf(threat([event(outside.lat, outside.lon, 1)]), HOME)?.nearHome).toBe(false)
  })

  it('drops the trend once the track is closed — a downed target moves nowhere', () => {
    const near = northOfHome(6)
    const far = northOfHome(20)
    const events = [event(near.lat, near.lon, 1), event(far.lat, far.lon, 5)]
    const closes = [
      { closed_reason: 'destroyed', status: 'destroyed' },
      { closed_reason: 'stale', status: 'lost' }, // "lost" is the stale close
    ] as const
    for (const close of closes) {
      const d = homeDistanceOf(
        threat(events, 'district', { closed_at: '2026-08-08T22:06:00', ...close }),
        HOME,
      )
      expect(d?.trend).toBeNull()
      expect(d?.km).toBeCloseTo(20, 0) // the distance itself still stands
    }
  })

  it('drops the trend for an impact — that is a place, not a movement', () => {
    const p = northOfHome(6)
    const q = northOfHome(4)
    const d = homeDistanceOf(
      threat([event(p.lat, p.lon, 1), event(q.lat, q.lon, 5)], 'district', {
        kind: 'impact',
        status: 'impact',
      }),
      HOME,
    )
    expect(d?.trend).toBeNull()
  })

  it('says nothing for a city-wide threat or one with no located sighting', () => {
    const p = northOfHome(5)
    expect(homeDistanceOf(threat([event(p.lat, p.lon, 1)], 'city'), HOME)).toBeNull()
    expect(homeDistanceOf(threat([event(null, null, 1)]), HOME)).toBeNull()
    expect(homeDistanceOf(threat([]), HOME)).toBeNull()
  })
})

describe('sightingDistanceOf', () => {
  // The 2026-08-31 report: five feed cards over Боярка, Теремки, Жуляни and
  // Голосіїв all read «~18 км». They were one track, and every row was
  // measuring the track's LATEST position instead of its own place.
  const BOYARKA = event(50.32, 30.29, 25) // ~20 km SW of HOME
  const GOLOSIIV = event(50.38, 30.51, 27) // ~8 km S of HOME

  it('measures the sighting, not the track it belongs to', () => {
    const track = threat([BOYARKA, GOLOSIIV])
    // The track reads as one number, correctly — that is the popup's question.
    const trackKm = homeDistanceOf(track, HOME)!.km
    // Each sighting reads as its own, and the two differ by more than rounding.
    const boyarka = sightingDistanceOf(BOYARKA, HOME)!
    const golosiiv = sightingDistanceOf(GOLOSIIV, HOME)!
    expect(Math.abs(boyarka.km - golosiiv.km)).toBeGreaterThan(5)
    // The newest sighting is what the track shows, so only that one agrees.
    expect(golosiiv.km).toBeCloseTo(trackKm, 5)
    expect(boyarka.km).not.toBeCloseTo(trackKm, 1)
  })

  it('needs no track events, so it survives a page reload', () => {
    // /events/recent serves feed rows through threat_out_shallow, whose
    // `events` is always [] — anything track-derived is simply absent there,
    // which is why the badge used to vanish on refresh.
    expect(homeDistanceOf(threat([]), HOME)).toBeNull()
    expect(sightingDistanceOf(GOLOSIIV, HOME)).not.toBeNull()
  })

  it('points from home toward the place, not away from it', () => {
    // Голосіїв is south of HOME, so the arrow points down-ish (180°±).
    expect(sightingDistanceOf(GOLOSIIV, HOME)!.bearingFromHome).toBeGreaterThan(150)
    expect(sightingDistanceOf(GOLOSIIV, HOME)!.bearingFromHome).toBeLessThan(210)
  })

  it('flags only a sighting inside the home zone plus its buffer', () => {
    expect(sightingDistanceOf(BOYARKA, HOME)!.nearHome).toBe(false)
    expect(sightingDistanceOf(event(HOME.lat, HOME.lon, 1), HOME)!.nearHome).toBe(true)
  })

  it('returns null for a sighting that never resolved to a place', () => {
    expect(sightingDistanceOf(event(null, null, 3), HOME)).toBeNull()
  })
})
