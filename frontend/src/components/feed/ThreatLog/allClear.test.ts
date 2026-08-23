import { describe, expect, it } from 'vitest'

import { durationLabel } from '@/lib/duration'
import type { Alert, Notice, TargetType } from '@/types'

import { CLEAR_TAILS, alertForClear, clearTailKey } from './allClear'

function notice(at: string, targetType: TargetType = 'unknown'): Notice {
  return {
    id: 1,
    kind: 'clear',
    text: 'Відбій тривоги',
    target_type: targetType,
    event_time: at,
  } as unknown as Notice
}

function alert(id: number, startedAt: string, endedAt: string | null): Alert {
  return {
    id,
    scope: 'city',
    alert_type: 'air',
    started_at: startedAt,
    ended_at: endedAt,
    provider: 'kmda',
  } as unknown as Alert
}

describe('matching an all-clear to the alert it closed', () => {
  it('finds the alert that ended alongside it', () => {
    const a = alert(1, '2026-08-23T00:27:00Z', '2026-08-23T02:14:00Z')
    expect(alertForClear([a], notice('2026-08-23T02:15:00Z'))).toBe(a)
  })

  it('ignores an alert that ended hours away', () => {
    const a = alert(1, '2026-08-22T20:00:00Z', '2026-08-22T21:00:00Z')
    expect(alertForClear([a], notice('2026-08-23T02:15:00Z'))).toBeNull()
  })

  it('picks the NEAREST end, not the newest alert', () => {
    // Two raids an hour apart: the notice belongs beside the one it sits next
    // to, and "newest" would have labelled it with the wrong duration.
    const early = alert(1, '2026-08-23T00:00:00Z', '2026-08-23T01:00:00Z')
    const late = alert(2, '2026-08-23T03:00:00Z', '2026-08-23T04:00:00Z')
    expect(alertForClear([late, early], notice('2026-08-23T01:02:00Z'))).toBe(early)
  })

  it('never labels a TYPE-SCOPED stand-down with the alert duration', () => {
    // «Відбій балістичної загрози» ends one kind of threat while the raid runs
    // on. Showing the alert's duration there would tell the reader the тривога
    // is over when it is not.
    const a = alert(1, '2026-08-23T00:27:00Z', '2026-08-23T02:14:00Z')
    expect(alertForClear([a], notice('2026-08-23T02:15:00Z', 'ballistic'))).toBeNull()
  })

  it('ignores an alert that is still running', () => {
    const a = alert(1, '2026-08-23T00:27:00Z', null)
    expect(alertForClear([a], notice('2026-08-23T02:15:00Z'))).toBeNull()
  })
})

describe('durationLabel', () => {
  // Stands in for i18next: asserts on the KEY chosen and the numbers fed to it,
  // which is the whole decision this function makes.
  const t = (key: string, vars: Record<string, number>) =>
    `${key}(${Object.entries(vars)
      .map(([k, v]) => `${k}=${v}`)
      .join(',')})`

  it('reads as minutes under an hour', () => {
    expect(durationLabel(t, '2026-08-23T02:00:00Z', '2026-08-23T02:47:00Z')).toBe('zones.m(m=47)')
  })

  it('reads as hours and minutes above one', () => {
    expect(durationLabel(t, '2026-08-23T00:27:00Z', '2026-08-23T02:14:00Z')).toBe(
      'zones.hm(h=1,m=47)',
    )
  })

  it('never reports zero — a forty-second alert still lasted', () => {
    expect(durationLabel(t, '2026-08-23T02:00:00Z', '2026-08-23T02:00:40Z')).toBe('zones.m(m=1)')
  })
})

describe('picking the closing half of the sentence', () => {
  it('gives the same notice the same tail every time', () => {
    // The card re-renders on every store change — several times a second during
    // a raid. Math.random() would have the sentence flickering between three
    // wordings while someone is reading it.
    const picks = Array.from({ length: 20 }, () => clearTailKey(591))
    expect(new Set(picks).size).toBe(1)
  })

  it('spreads a run of consecutive notices over every wording', () => {
    // The property that actually matters, and the one a bare `id % length`
    // failed: the official channel's all-clears arrive at a fixed id stride, so
    // seven of the eight most recent real ones came out identical. Asserted
    // over a run rather than a handful, and derived from CLEAR_TAILS so adding
    // a wording keeps this honest instead of silently passing.
    const ids = Array.from({ length: 200 }, (_, i) => 500 + i)
    const counts = new Map<string, number>()
    for (const id of ids) {
      const key = clearTailKey(id)
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    expect(counts.size).toBe(CLEAR_TAILS.length)
    // No wording may swallow the feed: an even split is 25%, so half is a
    // generous ceiling that still catches a collapse back to one or two.
    expect(Math.max(...counts.values())).toBeLessThan(ids.length / 2)
  })

  it('spreads them even when the ids arrive at a stride', () => {
    const ids = Array.from({ length: 100 }, (_, i) => 500 + i * CLEAR_TAILS.length)
    expect(new Set(ids.map(clearTailKey)).size).toBe(CLEAR_TAILS.length)
  })

  it('survives an id of 0 and a negative one', () => {
    expect(CLEAR_TAILS).toContain(clearTailKey(0))
    expect(CLEAR_TAILS).toContain(clearTailKey(-7))
  })

  it.each(['uk', 'en'] as const)('has every tail translated in %s', async (lang) => {
    const bundle = (await import(`../../../locales/${lang}.json`)).default as {
      notice: Record<string, unknown>
    }
    for (const key of CLEAR_TAILS) {
      expect(typeof bundle.notice[key.replace('notice.', '')]).toBe('string')
    }
    // The tails are referenced through CLEAR_TAILS, so locales/keys.test.ts —
    // which scans for literal t('…') call sites — cannot see them. This is
    // what stands in for it.
    expect(typeof bundle.notice.clearBody).toBe('string')
  })
})
