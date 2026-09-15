/** Formatting for the «Зараз онлайн» rows. Pure, so the guesswork in
 * `clientLabel` is testable without a table around it. */

/** A readable guess at what a reader is using, from their User-Agent.
 *
 * A guess by nature — a UA string is whatever the client chose to send, and
 * every browser lies about being the others. It is here to help the operator
 * tell two rows apart at a glance, never to be counted on, so the order below
 * is "most specific claim first" and anything unrecognised falls through to a
 * dash rather than to a wrong name.
 */
export function clientLabel(ua: string | null | undefined): string {
  if (!ua) return '—'
  const browser = browserOf(ua)
  const platform = platformOf(ua)
  if (browser && platform) return `${browser} · ${platform}`
  return browser || platform || '—'
}

function browserOf(ua: string): string | null {
  // Order matters: Edge and Opera both carry "Chrome", and every iOS browser
  // carries "Safari".
  if (/\bEdg\//.test(ua)) return 'Edge'
  if (/\bOPR\/|\bOpera/.test(ua)) return 'Opera'
  if (/\bSamsungBrowser\//.test(ua)) return 'Samsung'
  if (/\bFirefox\/|\bFxiOS\//.test(ua)) return 'Firefox'
  if (/\bCriOS\//.test(ua)) return 'Chrome'
  if (/\bChrome\//.test(ua)) return 'Chrome'
  if (/\bSafari\//.test(ua)) return 'Safari'
  return null
}

function platformOf(ua: string): string | null {
  // The TV before Android: Tizen's UA says both, and which one it is is the
  // whole reason this app carries a separate build target.
  if (/\bTizen\b|SMART-TV|\bTV\b/.test(ua)) return 'TV'
  if (/\biPhone\b/.test(ua)) return 'iPhone'
  if (/\biPad\b/.test(ua)) return 'iPad'
  if (/\bAndroid\b/.test(ua)) return 'Android'
  if (/\bWindows\b/.test(ua)) return 'Windows'
  if (/\bMac OS X\b|\bMacintosh\b/.test(ua)) return 'Mac'
  if (/\bLinux\b/.test(ua)) return 'Linux'
  return null
}

/** How long this reader has been connected, in the console's own Ukrainian.
 *
 * Its own formatter rather than `lib/duration`: that one needs the i18n `t`,
 * and the admin console is Ukrainian-only by design (see UsersPanel). Under a
 * minute reads «щойно» — a live view refreshed every few seconds would
 * otherwise spend most of its time showing "0 хв".
 */
export function sinceLabel(iso: string, now: number = Date.now()): string {
  const mins = Math.floor((now - new Date(iso).getTime()) / 60_000)
  if (!Number.isFinite(mins) || mins < 1) return 'щойно'
  if (mins < 60) return `${mins} хв`
  const hours = Math.floor(mins / 60)
  const rest = mins % 60
  return rest ? `${hours} год ${rest} хв` : `${hours} год`
}

/** Enough of a device id to tell rows apart, without a 36-character column. */
export function shortDevice(id: string | null | undefined): string {
  if (!id) return '—'
  return id.length <= 10 ? id : `${id.slice(0, 8)}…`
}
