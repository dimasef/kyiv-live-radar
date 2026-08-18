import { afterEach, describe, expect, it, vi } from 'vitest'

/** The feed's day grouping used to construct `Intl.DateTimeFormat` with
 * `timeZone: 'Europe/Kyiv'` directly. On a TV browser (Samsung Internet on
 * Tizen) that throws RangeError — a trimmed ICU with no tz database — and since
 * it ran while rendering the first timestamp, React unmounted the whole tree and
 * the screen went black the moment messages arrived. These tests simulate that
 * engine and require the timeline to keep working. */
function breakTimeZones() {
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
  return import('./timeline')
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('feed timeline on an engine without time-zone data', () => {
  it('still groups by the Kyiv calendar day', async () => {
    const { kyivDayKey } = await breakTimeZones()
    // 22:30 UTC in July is 01:30 Kyiv the next day.
    expect(kyivDayKey(new Date('2026-07-10T22:30:00Z'))).toBe('2026-07-11')
  })

  it('still labels a day separator', async () => {
    const { daySeparatorLabel } = await breakTimeZones()
    const t = (key: string) => key
    expect(daySeparatorLabel('2026-07-10', 'uk', t)).toBe('10 липня')
    // Today/yesterday still resolve against the same Kyiv clock.
    const { kyivDayKey } = await import('./timeline')
    expect(daySeparatorLabel(kyivDayKey(new Date()), 'uk', t)).toBe('log.today')
  })
})
