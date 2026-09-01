import { describe, expect, it } from 'vitest'

import type { Alert, FeedEntry, Incident, Notice, Region } from '@/types'

import {
  buildTimeline,
  filterFeedAlerts,
  filterFeedIncidents,
  filterFeedNotices,
  filterFeedRegions,
} from './timeline'

// The reader's chosen set. HOME is what `shownRegions` guarantees is always in
// it — no stored state can produce a set without the home region.
const HOME = new Set<Region>(['kyiv'])
const HOME_AND_NORTH = new Set<Region>(['kyiv', 'chernihiv'])

let nextId = 1

function entry(region: Region, over = 'ціль'): FeedEntry {
  const id = nextId++
  return {
    event: {
      id,
      threat_id: id,
      raw_text: over,
      event_time: `2026-08-20T0${id}:00:00Z`,
      source_id: 1,
      source_message_id: id,
    },
    threat: { id, region, target_type: 'shahed', events: [] },
  } as unknown as FeedEntry
}

describe('regions in the feed', () => {
  it('keeps everything when other regions are on', () => {
    const log = [entry('kyiv'), entry('chernihiv')]
    expect(filterFeedRegions(log, HOME_AND_NORTH)).toHaveLength(2)
  })

  it('drops the other regions when they are off', () => {
    const kyiv = entry('kyiv')
    const log = [kyiv, entry('chernihiv'), entry('chernihiv')]
    expect(filterFeedRegions(log, HOME)).toEqual([kyiv])
  })

  it('keeps the chosen regions and drops the rest', () => {
    // The whole point of a set over a boolean: opting into one approach region
    // must not opt you into every other one.
    const log = [entry('kyiv'), entry('chernihiv'), entry('sumy')]
    const shown = filterFeedRegions(log, HOME_AND_NORTH)
    expect(shown.map((e) => e.threat.region)).toEqual(['kyiv', 'chernihiv'])
  })

  it('filters a copy, leaving the stored log intact', () => {
    // Flipping the toggle back must restore what was already received without
    // a refetch — so the filter may never mutate the log it was handed.
    const log = [entry('kyiv'), entry('chernihiv')]
    filterFeedRegions(log, HOME)
    expect(log).toHaveLength(2)
  })

  it('reaches the rendered timeline', () => {
    const log = [entry('kyiv'), entry('chernihiv')]
    const shown = buildTimeline(filterFeedRegions(log, HOME), [], [])
    expect(shown).toHaveLength(1)
    expect(shown[0].kind).toBe('group')
  })
})

function notice(region: Region | undefined, kind = 'directional'): Notice {
  const id = nextId++
  return {
    id,
    kind,
    text: 'з Брянської',
    target_type: 'jet_drone',
    event_time: `2026-08-20T0${id % 10}:00:00Z`,
    source_id: 1,
    source_name: 'Чисте Небо',
    region,
  } as unknown as Notice
}

describe('regions in the feed — notices', () => {
  it('drops the other regions when they are off', () => {
    const kyiv = notice('kyiv')
    expect(filterFeedNotices([kyiv, notice('chernihiv'), notice('chernihiv')], HOME)).toEqual([
      kyiv,
    ])
  })

  it('keeps everything when other regions are on', () => {
    expect(filterFeedNotices([notice('kyiv'), notice('chernihiv')], HOME_AND_NORTH)).toHaveLength(2)
  })

  it('keeps a notice with no region — an official all-clear has no channel', () => {
    expect(filterFeedNotices([notice(undefined)], HOME)).toHaveLength(1)
  })

  it('reaches the rendered timeline', () => {
    // The 2026-08-21 screenshot: a Kyiv-filtered feed opening with seven
    // consecutive Чернігівщина «напрямок загрози» cards.
    const shown = buildTimeline([], filterFeedNotices([notice('chernihiv')], HOME), [])
    expect(shown).toHaveLength(0)
  })
})


// An incident has no region of its own: it is a Kyiv attack by construction
// (ingest/handlers._incident_broadcast returns None outside the home region),
// but it now SAYS so on the wire instead of leaving the client to assume it —
// so the filter tests the incident's own region, and a non-Kyiv one is
// expressible here the day that gate lifts.
function incident(region: Region = 'kyiv'): Incident {
  const id = nextId++
  return {
    id,
    region,
    started_at: '2026-08-29T17:35:00Z',
    ended_at: '2026-08-29T17:47:00Z',
    ended_reason: 'all_clear',
    classification: 'drone',
    track_count: 1,
    target_count: 1,
    district_count: 1,
  } as unknown as Incident
}

const SUMY_ONLY = new Set<Region>(['sumy'])

describe('regions in the feed — attack summaries', () => {
  it('drops the Kyiv rollups for a reader who is not watching Kyiv', () => {
    expect(filterFeedIncidents([incident(), incident()], SUMY_ONLY)).toEqual([])
  })

  it('keeps them for a reader who is', () => {
    expect(filterFeedIncidents([incident()], HOME)).toHaveLength(1)
    expect(filterFeedIncidents([incident()], HOME_AND_NORTH)).toHaveLength(1)
  })

  it('keeps another region\'s attack for a reader watching that region', () => {
    // Not reachable today (only the home region opens incidents), and the
    // point of testing it: this is what the column buys — the gate can lift
    // without a second pass over everything that reads an incident.
    expect(filterFeedIncidents([incident('sumy')], SUMY_ONLY)).toHaveLength(1)
    expect(filterFeedIncidents([incident('sumy')], HOME)).toEqual([])
  })

  it('reaches the rendered timeline', () => {
    // The 2026-08-29 screenshot: a Сумщина-only feed showing three «АТАКУ
    // ЗАВЕРШЕНО» cards. They read as unpaired because the feed has no
    // attack-START card at all — buildTimeline only ever emits 'incidentEnd'.
    const shown = buildTimeline([], [], filterFeedIncidents(
      [incident(), incident(), incident()], SUMY_ONLY))
    expect(shown).toHaveLength(0)
  })

  it('still renders them when Kyiv is on, so the filter is not a blanket mute', () => {
    const shown = buildTimeline([], [], filterFeedIncidents([incident()], HOME))
    expect(shown).toHaveLength(1)
    expect(shown[0].kind).toBe('incidentEnd')
  })
})

describe('alerts in the feed', () => {
  const BROVARY = 'kyiv-obl-brovarskyi'

  function alert(over: Partial<Alert>): Alert {
    return {
      id: nextId++,
      region: 'kyiv',
      scope: 'city',
      zone_id: null,
      alert_type: 'air_raid',
      started_at: '2026-08-20T22:00:00Z',
      ended_at: null,
      provider: 'telegram',
      closed_reason: null,
      ...over,
    } as Alert
  }

  const AT_HOME = { zoneId: BROVARY, region: 'kyiv' as Region }

  it('keeps only the reader\'s own raion', () => {
    // A region-wide siren staggers across seven raions; the region-level filter
    // the other feed inputs use would have posted seven cards for one event.
    const mine = alert({ scope: 'raion', zone_id: BROVARY })
    const neighbour = alert({ scope: 'raion', zone_id: 'kyiv-obl-buchanskyi' })
    expect(filterFeedAlerts([mine, neighbour], AT_HOME)).toEqual([mine])
  })

  it('drops a secondary feed region\'s alerts, unlike its sightings', () => {
    // A sighting over Чернігівщина is something to watch happening elsewhere.
    // A siren there is an instruction to take shelter — and it is not the
    // reader's, however much of that region their feed lists.
    const north = alert({ region: 'chernihiv', scope: 'raion', zone_id: 'chernihiv-obl-nizhynskyi' })
    expect(filterFeedAlerts([north], AT_HOME)).toEqual([])
    expect(filterFeedRegions([entry('chernihiv')], HOME_AND_NORTH)).toHaveLength(1)
  })

  it('emits a start card for every alert', () => {
    const shown = buildTimeline([], [], [], [alert({ scope: 'raion', zone_id: BROVARY })])
    expect(shown.map((i) => i.kind)).toEqual(['alertStart'])
  })

  it('emits an end card for a raion alert but not for the official channel\'s', () => {
    // The official відбій already arrives as a Notice(kind='clear') and renders
    // as AllClearCard — a second card here would print the all-clear twice.
    const ended = { ended_at: '2026-08-20T23:30:00Z', closed_reason: 'official' as const }
    const raion = alert({ scope: 'raion', zone_id: BROVARY, ...ended })
    const official = alert({ scope: 'city', ...ended })
    const kinds = buildTimeline([], [], [], [raion, official]).map((i) => i.kind)
    expect(kinds.filter((k) => k === 'alertStart')).toHaveLength(2)
    expect(kinds.filter((k) => k === 'alertEnd')).toHaveLength(1)
  })

  it('drops an admin-dismissed alert entirely', () => {
    const bogus = alert({
      scope: 'raion', zone_id: BROVARY,
      ended_at: '2026-08-20T22:05:00Z', closed_reason: 'dismissed',
    })
    expect(buildTimeline([], [], [], [bogus])).toEqual([])
  })
})
