import { afterEach, describe, expect, it, vi } from 'vitest'

import { kyivClock, kyivDayKey, kyivDayMonth, kyivStamp } from './kyivTime'

/** Re-import the module with `Intl.DateTimeFormat` refusing IANA time zones —
 * what Samsung Internet on a Tizen TV does (trimmed ICU, no tz database). The
 * probe runs at module load, so the registry has to be reset. */
async function withoutTimeZoneSupport() {
  const Real = Intl.DateTimeFormat
  vi.stubGlobal(
    'Intl',
    Object.assign(Object.create(Intl), {
      DateTimeFormat: function (locale?: string, options?: Intl.DateTimeFormatOptions) {
        if (options?.timeZone && options.timeZone !== 'UTC') {
          throw new RangeError(`Invalid time zone specified: ${options.timeZone}`)
        }
        return new Real(locale, options)
      },
    }),
  )
  vi.resetModules()
  return import('./kyivTime')
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('with a full ICU (desktop/phone)', () => {
  it('formats the clock in Kyiv time, 24-hour', () => {
    // 19:05 UTC in July is 22:05 Kyiv (EEST, UTC+3).
    expect(kyivClock('2026-07-10T19:05:00Z')).toBe('22:05')
    // 19:05 UTC in January is 21:05 Kyiv (EET, UTC+2).
    expect(kyivClock('2026-01-10T19:05:00Z')).toBe('21:05')
  })

  it('buckets the day by Kyiv midnight, not UTC', () => {
    expect(kyivDayKey(new Date('2026-07-10T22:30:00Z'))).toBe('2026-07-11')
    expect(kyivDayKey(new Date('2026-07-10T20:30:00Z'))).toBe('2026-07-10')
  })

  it('formats midnight as 00:00, never 24:00', () => {
    expect(kyivClock('2026-07-10T21:00:00Z')).toBe('00:00')
  })

  it('returns a dash for a missing or unparseable timestamp', () => {
    expect(kyivClock(null)).toBe('—')
    expect(kyivClock('not a date')).toBe('—')
    expect(kyivStamp(undefined)).toBe('—')
    expect(kyivDayKey(new Date('nope'))).toBe('')
  })

  it('formats a full stamp and a localized day/month', () => {
    expect(kyivStamp('2026-08-18T07:09:00Z')).toBe('18.08.2026, 10:09')
    expect(kyivDayMonth(new Date('2026-08-18T07:09:00Z'), 'uk-UA')).toContain('18')
  })
})

describe('on an engine with no time-zone data (TV browser)', () => {
  it('still renders Kyiv summer time instead of throwing', async () => {
    const tz = await withoutTimeZoneSupport()
    expect(tz.hasTimeZoneSupport).toBe(false)
    expect(tz.kyivClock('2026-07-10T19:05:00Z')).toBe('22:05')
    expect(tz.kyivDayKey(new Date('2026-07-10T22:30:00Z'))).toBe('2026-07-11')
  })

  it('still renders Kyiv winter time', async () => {
    const tz = await withoutTimeZoneSupport()
    expect(tz.kyivClock('2026-01-10T19:05:00Z')).toBe('21:05')
    expect(tz.kyivStamp('2026-01-10T19:05:00Z')).toBe('10.01.2026, 21:05')
  })

  it('picks the right side of both DST switches', async () => {
    const tz = await withoutTimeZoneSupport()
    // Kyiv springs forward at 01:00 UTC on the last Sunday of March 2026 (29th).
    expect(tz.kyivClock('2026-03-29T00:30:00Z')).toBe('02:30')
    expect(tz.kyivClock('2026-03-29T01:30:00Z')).toBe('04:30')
    // …and falls back at 01:00 UTC on the last Sunday of October (25th).
    expect(tz.kyivClock('2026-10-25T00:30:00Z')).toBe('03:30')
    expect(tz.kyivClock('2026-10-25T01:30:00Z')).toBe('03:30')
  })

  it('falls back to built-in month names', async () => {
    const tz = await withoutTimeZoneSupport()
    expect(tz.kyivDayMonth(new Date('2026-08-18T07:09:00Z'), 'uk-UA')).toBe('18 серпня')
    expect(tz.kyivDayMonth(new Date('2026-08-18T07:09:00Z'), 'en-US')).toBe('18 August')
  })
})
