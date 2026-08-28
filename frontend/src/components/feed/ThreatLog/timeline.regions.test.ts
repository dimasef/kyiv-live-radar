import { describe, expect, it } from 'vitest'

import type { FeedEntry, Notice, Region } from '@/types'

import { buildTimeline, filterFeedNotices, filterFeedRegions } from './timeline'

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
