// Emits a real HTML file per indexable route, after `vite build`.
//
// Without this every URL is served the ONE `dist/index.html`, whose head says
// `<title>UA Live Radar — мапа повітряних загроз</title>` and, worse,
// `<link rel="canonical" href="https://www.ua-radar.online/">`. The app fixes
// both client-side (lib/documentMeta.ts) — but a canonical that only exists
// after JS has run is the one signal Google explicitly says not to rely on, so
// /journal was shipping a declaration that it is a duplicate of the homepage.
// The sitemap listed it; the HTML told Google to drop it.
//
// The same head is what Telegram, Signal and Viber read when someone shares a
// link, and those never run JS at all — so every shared /journal link used to
// preview as the homepage.
//
// Not prerendering the BODY: that would need a headless browser and a live
// backend, and the body of these routes is data that changes hourly. The head
// is the part that is stable, and the part that was wrong.
//
// Vercel checks the filesystem before applying `rewrites` (vercel.json), so
// `dist/journal/index.html` wins over the SPA fallback for /journal on its own.

import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const DIST = join(ROOT, 'dist')
const ORIGIN = 'https://www.ua-radar.online'
// Where the day list comes from at build time. Vercel sets VITE_API_URL; the
// fallback is the production backend, so a local `npm run build` produces the
// same pages as a deploy rather than silently skipping them.
const API = process.env.VITE_API_URL ?? 'https://kyiv-live-radar-production.up.railway.app'
// /journal/days refuses a range wider than this (backend api/public/journal.py).
const WINDOW_DAYS = 92
// How far back to walk. Six windows is ~1.5 years — a bound, not an estimate.
const MAX_WINDOWS = 6

const uk = JSON.parse(await readFile(join(ROOT, 'src/locales/uk.json'), 'utf8'))
const APP = uk.app.title

// Names come from the app's own copy so the brand and the tab labels can never
// drift from what the UI says. The descriptions live here because they exist
// nowhere else — they are written for a search result, not for a screen.
const ROUTES = [
  {
    path: '/journal',
    name: uk.nav.journal,
    description:
      'Журнал повітряних атак по днях: скільки цілей, яких типів і скільки тривала тривога над Київщиною, Чернігівщиною та Сумщиною.',
  },
  {
    path: '/journal/stats',
    name: `${uk.nav.journal} · ${uk.journal.tabs.stats}`,
    description:
      'Статистика повітряних атак за період: динаміка по днях, типи цілей, тривалість тривог над Київщиною, Чернігівщиною та Сумщиною.',
  },
  {
    path: '/change-log',
    name: uk.changelog.title,
    description: `Історія версій ${APP} — що змінилось у мапі повітряних загроз.`,
  },
]

const MONTHS_GENITIVE = [
  'січня', 'лютого', 'березня', 'квітня', 'травня', 'червня',
  'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня',
]

/** «14 вересня 2026» — the same shape lib/documentMeta.ts produces, so the head
 * a crawler is served and the title the app sets on arrival agree. Built from
 * the ISO parts, never from a Date: this names a Kyiv calendar day, not an
 * instant, and must not shift under a build machine's timezone. */
function dayLabel(iso) {
  const [y, m, d] = iso.split('-')
  return `${Number(d)} ${MONTHS_GENITIVE[Number(m) - 1]} ${y}`
}

/** Ukrainian counts: 1 ціль, 2 цілі, 5 цілей. Three forms, and the rule keys
 * on the last two digits — «21 ціль» but «11 цілей». This text is read in a
 * search result, where «22 цілей» is not a rounding error, it is broken
 * Ukrainian on the only line of ours that a stranger sees. */
function plural(n, [one, few, many]) {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return `${n} ${one}`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} ${few}`
  return `${n} ${many}`
}

function isoShift(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Whether a day is worth its own address.
 *
 * Deliberately NARROWER than the calendar's own `hasActivity`: this decides
 * what gets published, and a page with nothing on it is the one kind of page
 * worth not having. Erring on the side of leaving a day out costs one URL;
 * erring the other way is a thin page in the index.
 */
function worthPublishing(day) {
  return day.attack_count > 0 || day.target_count > 0 || day.impact_count > 0 || day.alert_count > 0
}

/** Every past day that has something to show, newest first.
 *
 * Walks backwards a window at a time because the endpoint caps a range at 92
 * days. Stops at the first entirely empty window: this feed has produced
 * activity most days since launch, so a silent quarter means we have walked
 * off the start of the data, not over a gap.
 */
async function fetchPublishableDays() {
  const out = []
  let end = new Date().toISOString().slice(0, 10)
  for (let i = 0; i < MAX_WINDOWS; i++) {
    const from = isoShift(end, -(WINDOW_DAYS - 1))
    const res = await fetch(`${API}/journal/days?from=${from}&to=${end}`)
    if (!res.ok) throw new Error(`GET /journal/days ${from}..${end} -> ${res.status}`)
    const { days = [] } = await res.json()
    const active = days.filter(worthPublishing)
    out.push(...active)
    if (active.length === 0) break
    end = isoShift(from, -1)
  }
  return out.sort((a, b) => (a.date < b.date ? 1 : -1))
}

const shell = await readFile(join(DIST, 'index.html'), 'utf8')

/** Replace an attribute's value on the one tag a selector-ish pattern matches.
 * A regex rather than a DOM parser: this runs on our own file, whose exact
 * shape is in index.html next door, and pulling in a parser for four tags is
 * more moving parts than the job is worth. */
function setAttr(html, pattern, value) {
  const next = html.replace(pattern, (m, pre) => `${pre}${value}"`)
  if (next === html) throw new Error(`prerender: nothing matched ${pattern}`)
  return next
}

const esc = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

/** `<meta name="description" content="…">` — with any whitespace between the
 * attributes, because index.html wraps the long ones over several lines and
 * Vite copies it through verbatim. */
const metaTag = (attr, key) =>
  new RegExp(`(<meta\\s+${attr}="${key}"\\s+content=")[^"]*"`)

/** One route's head, written onto the built shell. */
function pageHtml({ title, description, url }) {
  let html = shell
  html = html.replace(/<title>[^<]*<\/title>/, `<title>${esc(title)}</title>`)
  html = setAttr(html, /(<link\s+rel="canonical"\s+href=")[^"]*"/, esc(url))
  html = setAttr(html, metaTag('property', 'og:url'), esc(url))
  html = setAttr(html, metaTag('property', 'og:title'), esc(title))
  html = setAttr(html, metaTag('name', 'twitter:title'), esc(title))
  html = setAttr(html, metaTag('name', 'description'), esc(description))
  html = setAttr(html, metaTag('property', 'og:description'), esc(description))
  html = setAttr(html, metaTag('name', 'twitter:description'), esc(description))
  return html
}

async function emit(path, html) {
  const dir = join(DIST, path)
  await mkdir(dir, { recursive: true })
  await writeFile(join(dir, 'index.html'), html)
}

for (const route of ROUTES) {
  const title = `${route.name} — ${APP}`
  const url = `${ORIGIN}${route.path}`
  await emit(route.path, pageHtml({ title, description: route.description, url }))
  console.log(`prerendered ${route.path}/index.html`)
}

// --- One page per day of the journal ------------------------------------
//
// The only durable content this app has: the map is live and gone, but «що
// літало 14 вересня» stays true forever and is a question people actually
// type. Each day gets a real file so the head is right for a crawler and for a
// link preview — the SPA fallback would hand every one of them the homepage's
// canonical (that is the bug this script exists for).
//
// A day newer than the last deploy has no file yet and falls through to that
// fallback: still a working page, just with the canonical only JS fixes. It
// gets its file at the next deploy, which for a daily-updating site is soon
// enough — and the alternative, rendering on demand, is a server this
// deployment does not have.
let days = []
try {
  days = await fetchPublishableDays()
} catch (err) {
  // Never fail the build over this: a backend hiccup must not stop a frontend
  // deploy. The cost is that this build ships without day pages, so it is loud.
  console.warn(`\n  !! journal day pages SKIPPED: ${err.message}`)
  console.warn('     (the site still deploys; redeploy once the API answers)\n')
}

for (const day of days) {
  const label = dayLabel(day.date)
  const targets = day.target_count + day.impact_count
  // Real numbers, so no two of these pages describe themselves the same way —
  // which is also the difference between a day page and a doorway page.
  const parts = [
    targets > 0 ? plural(targets, ['ціль', 'цілі', 'цілей']) : null,
    day.alert_count > 0 ? plural(day.alert_count, ['тривога', 'тривоги', 'тривог']) : null,
  ].filter(Boolean)
  const description =
    `Повітряні загрози ${label}${parts.length ? `: ${parts.join(', ')}` : ''} над Київщиною, `
    + 'Чернігівщиною та Сумщиною — шахеди, ракети й КАБи за повідомленнями спостерігачів.'
  await emit(
    `/journal/${day.date}`,
    pageHtml({
      title: `${label} · ${uk.nav.journal} — ${APP}`,
      description,
      url: `${ORIGIN}/journal/${day.date}`,
    }),
  )
}
if (days.length) console.log(`prerendered ${days.length} journal day pages`)

// --- Sitemap ------------------------------------------------------------
// The static public/sitemap.xml stays the source for the fixed URLs; the days
// are appended here because only a build that has talked to the API knows them.
const base = await readFile(join(DIST, 'sitemap.xml'), 'utf8')
const dayUrls = days
  .map(
    (d) =>
      `  <url><loc>${ORIGIN}/journal/${d.date}</loc><lastmod>${d.date}</lastmod>`
      + '<changefreq>monthly</changefreq><priority>0.5</priority></url>',
  )
  .join('\n')
if (dayUrls) {
  await writeFile(join(DIST, 'sitemap.xml'), base.replace('</urlset>', `${dayUrls}\n</urlset>`))
  console.log(`sitemap: ${days.length} day URLs added`)
}
