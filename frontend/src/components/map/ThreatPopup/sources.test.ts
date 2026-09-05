import { describe, expect, it } from 'vitest'

import type { Threat, ThreatEvent } from '@/types'

import { sourceSplit } from './sources'

const ev = (source_id: number, source_name: string, manual = false): ThreatEvent =>
  ({ source_id, source_name, manual }) as ThreatEvent

describe('sourceSplit', () => {
  it('names the lead and counts the echo by channel', () => {
    const t = {
      path_source_id: 5,
      events: [ev(5, 'Місто Кия'), ev(12, 'Небо'), ev(13, 'Віраж'), ev(12, 'Небо'), ev(13, 'Віраж', true)],
    } as unknown as Threat
    expect(sourceSplit(t)).toEqual({ lead: 'Місто Кия', echoCount: 3, echoSources: ['Небо', 'Віраж'] })
  })

  it('has nothing to say for history without a path source', () => {
    const t = { path_source_id: null, events: [ev(5, 'Місто Кия')] } as unknown as Threat
    expect(sourceSplit(t)).toEqual({ lead: null, echoCount: 0, echoSources: [] })
  })
})
