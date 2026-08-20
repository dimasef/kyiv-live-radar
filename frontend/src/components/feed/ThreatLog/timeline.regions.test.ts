import { describe, expect, it } from 'vitest'

import type { FeedEntry, Region } from '@/types'

import { buildTimeline, filterFeedRegions } from './timeline'

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
    expect(filterFeedRegions(log, true)).toHaveLength(2)
  })

  it('drops the other regions when they are off', () => {
    const kyiv = entry('kyiv')
    const log = [kyiv, entry('chernihiv'), entry('chernihiv')]
    expect(filterFeedRegions(log, false)).toEqual([kyiv])
  })

  it('filters a copy, leaving the stored log intact', () => {
    // Flipping the toggle back must restore what was already received without
    // a refetch — so the filter may never mutate the log it was handed.
    const log = [entry('kyiv'), entry('chernihiv')]
    filterFeedRegions(log, false)
    expect(log).toHaveLength(2)
  })

  it('reaches the rendered timeline', () => {
    const log = [entry('kyiv'), entry('chernihiv')]
    const shown = buildTimeline(filterFeedRegions(log, false), [], [])
    expect(shown).toHaveLength(1)
    expect(shown[0].kind).toBe('group')
  })
})
