import { describe, expect, it } from 'vitest'

import { presenceLabel } from './presence'

const NOW = Date.parse('2026-08-01T22:00:00Z')
const ago = (minutes: number) => new Date(NOW - minutes * 60_000).toISOString()

describe('presenceLabel', () => {
  it('reports online without looking at the timestamp at all', () => {
    expect(presenceLabel({ online: true, lastSeenAt: null }, NOW)).toEqual({ kind: 'online' })
  })

  it('falls back to "never" when the server withheld the timestamp', () => {
    // The normal case for a friend who did NOT opt into sharing presence.
    expect(presenceLabel({ online: false, lastSeenAt: null }, NOW)).toEqual({ kind: 'never' })
    expect(presenceLabel({ online: false, lastSeenAt: undefined }, NOW)).toEqual({ kind: 'never' })
  })

  it('counts minutes under an hour', () => {
    expect(presenceLabel({ online: false, lastSeenAt: ago(0) }, NOW)).toEqual({
      kind: 'minutes',
      value: 0,
    })
    expect(presenceLabel({ online: false, lastSeenAt: ago(59) }, NOW)).toEqual({
      kind: 'minutes',
      value: 59,
    })
  })

  it('switches to hours at exactly one hour, and to days at 24', () => {
    expect(presenceLabel({ online: false, lastSeenAt: ago(60) }, NOW)).toEqual({
      kind: 'hours',
      value: 1,
    })
    expect(presenceLabel({ online: false, lastSeenAt: ago(60 * 23) }, NOW)).toEqual({
      kind: 'hours',
      value: 23,
    })
    expect(presenceLabel({ online: false, lastSeenAt: ago(60 * 24) }, NOW)).toEqual({
      kind: 'days',
      value: 1,
    })
  })

  it('clamps a server clock running ahead, instead of rendering a future', () => {
    expect(presenceLabel({ online: false, lastSeenAt: ago(-5) }, NOW)).toEqual({
      kind: 'minutes',
      value: 0,
    })
  })

  it('treats an unparseable timestamp as unknown rather than NaN', () => {
    expect(presenceLabel({ online: false, lastSeenAt: 'not-a-date' }, NOW)).toEqual({
      kind: 'never',
    })
  })
})
