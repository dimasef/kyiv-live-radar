/** Kyiv wall-clock formatting that survives engines without IANA time-zone data.
 *
 * Every timestamp in this app is UTC from the API and must be shown in Kyiv time,
 * so the obvious call is `Intl.DateTimeFormat(locale, { timeZone: 'Europe/Kyiv' })`.
 * On a TV browser (Samsung Internet on Tizen) that **throws** `RangeError:
 * Invalid time zone specified` — those builds ship a trimmed ICU with no tz
 * database. Thrown from a render, it unmounted the whole React tree and the
 * screen went black the moment the first feed timestamp appeared.
 *
 * Two more traps on the same engines, both handled here:
 * - a trimmed ICU has no `uk-UA` locale either, so it silently falls back to
 *   en-US and renders "10:00 PM" where Kyiv reads 22:00. Clock and day-key
 *   formats are therefore assembled from parts, never from a locale pattern.
 * - a bad/absent timestamp makes `format()` throw "Invalid time value"; every
 *   entry point returns a dash instead.
 */

const KYIV_TZ = 'Europe/Kyiv'
const DASH = '—'

/** Whether this engine can format an IANA time zone at all. Probed once: the
 * constructor is what throws, so a single successful call settles it. */
export const hasTimeZoneSupport: boolean = (() => {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: KYIV_TZ, hour: '2-digit' }).format(new Date(0))
    return true
  } catch {
    return false
  }
})()

function isValid(date: Date): boolean {
  return !Number.isNaN(date.getTime())
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/** 01:00 UTC on the last Sunday of `month0`, the EU DST switch instant. */
function euSwitch(year: number, month0: number): number {
  const lastDay = new Date(Date.UTC(year, month0 + 1, 0))
  lastDay.setUTCDate(lastDay.getUTCDate() - lastDay.getUTCDay())
  return Date.UTC(lastDay.getUTCFullYear(), lastDay.getUTCMonth(), lastDay.getUTCDate(), 1)
}

/** Kyiv's UTC offset in minutes: EET (+2) / EEST (+3) on the EU schedule. Only
 * used on engines with no tz database — where ICU is available it stays the
 * authority, so a future change to Ukraine's DST rules keeps working there. */
function kyivOffsetMinutes(date: Date): number {
  const t = date.getTime()
  const year = date.getUTCFullYear()
  return t >= euSwitch(year, 2) && t < euSwitch(year, 9) ? 180 : 120
}

/** `date` shifted so its **UTC** getters read as Kyiv wall-clock time. */
function kyivWallClock(date: Date): Date {
  return new Date(date.getTime() + kyivOffsetMinutes(date) * 60_000)
}

/** Kyiv-local Y/M/D/h/m, from ICU when it has the tz, by arithmetic otherwise. */
function kyivParts(date: Date): {
  year: number
  month: number
  day: number
  hour: number
  minute: number
} {
  if (hasTimeZoneSupport) {
    try {
      // Assembled from parts, never from the formatted string: on a trimmed ICU
      // the locale pattern is not ours to predict.
      const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: KYIV_TZ,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).formatToParts(date)
      const value = (type: string) => Number(parts.find((p) => p.type === type)?.value)
      const out = {
        year: value('year'),
        month: value('month'),
        day: value('day'),
        // 24-hour ICU reports midnight as hour 24 in some versions.
        hour: value('hour') % 24,
        minute: value('minute'),
      }
      if (!Object.values(out).some(Number.isNaN)) return out
    } catch {
      /* fall through to arithmetic */
    }
  }
  const w = kyivWallClock(date)
  return {
    year: w.getUTCFullYear(),
    month: w.getUTCMonth() + 1,
    day: w.getUTCDate(),
    hour: w.getUTCHours(),
    minute: w.getUTCMinutes(),
  }
}

/** `YYYY-MM-DD` of the Kyiv calendar day — the feed's day-grouping key. */
export function kyivDayKey(date: Date): string {
  if (!isValid(date)) return ''
  const p = kyivParts(date)
  return `${p.year}-${pad2(p.month)}-${pad2(p.day)}`
}

/** `HH:MM`, 24-hour, Kyiv. */
export function kyivClock(iso: string | Date | null | undefined): string {
  if (iso == null) return DASH
  const date = iso instanceof Date ? iso : new Date(iso)
  if (!isValid(date)) return DASH
  const p = kyivParts(date)
  return `${pad2(p.hour)}:${pad2(p.minute)}`
}

/** `DD.MM.YYYY, HH:MM` Kyiv — the admin tables' compact stamp. */
export function kyivStamp(iso: string | Date | null | undefined): string {
  if (iso == null) return DASH
  const date = iso instanceof Date ? iso : new Date(iso)
  if (!isValid(date)) return DASH
  const p = kyivParts(date)
  return `${pad2(p.day)}.${pad2(p.month)}.${p.year}, ${pad2(p.hour)}:${pad2(p.minute)}`
}

const MONTHS: Record<string, string[]> = {
  uk: [
    'січня',
    'лютого',
    'березня',
    'квітня',
    'травня',
    'червня',
    'липня',
    'серпня',
    'вересня',
    'жовтня',
    'листопада',
    'грудня',
  ],
  en: [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ],
}

/** "18 серпня" / "18 August" for a Kyiv day. Prefers ICU (proper genitive month
 * names, other locales) and falls back to a built-in month list. */
export function kyivDayMonth(date: Date, locale: string): string {
  if (!isValid(date)) return DASH
  if (hasTimeZoneSupport) {
    try {
      return new Intl.DateTimeFormat(locale, {
        timeZone: KYIV_TZ,
        day: 'numeric',
        month: 'long',
      }).format(date)
    } catch {
      /* fall through */
    }
  }
  const p = kyivParts(date)
  const names = MONTHS[locale.slice(0, 2)] ?? MONTHS.en
  return `${p.day} ${names[p.month - 1]}`
}
