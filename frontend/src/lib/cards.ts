import type { AnalysisKind } from '@/api'
import type { Threat } from '@/types'

/** Rarity drives BOTH the card-frame tint and the drop odds: rarer cards drop
 * less often. The weights live on the backend (app/domain/cards.RARITY_WEIGHT +
 * CARD_RARITY), which must mirror the `rarity` set here — this catalog stays the
 * source of truth for each card's rarity. */
export type Rarity = 'common' | 'rare' | 'legendary'

export interface CardDef {
  id: number
  title: string
  flavor: string
  rarity: Rarity
}

/** The collectible deck. `id` MUST stay 1..N contiguous and in sync with the
 * backend's CARD_COUNT (app/domain/cards.py) — the server only stores the id,
 * all art/copy lives here. The per-card SVG glyph lives in CardGlyph.tsx, keyed
 * by id. Content is Ukrainian by design (the whole domain is). Rarity per id
 * MUST match the backend CARD_RARITY (drop weighting). */
export const CARDS: CardDef[] = [
  { id: 1, title: 'Тінь у небі', rarity: 'common', flavor: 'Силует «шахеда» на тлі зірок. Чути — значить ще летить.' },
  { id: 2, title: 'Балістичний слід', rarity: 'legendary', flavor: 'Розжарена лінія за секунди. Найшвидша і найтихіша загроза.' },
  { id: 3, title: 'Робота ППО', rarity: 'rare', flavor: 'Той звук, після якого стає легше дихати.' },
  { id: 4, title: 'Уламки на світанку', rarity: 'common', flavor: 'Те, що лишається від цілі, яка не долетіла.' },
  { id: 5, title: 'Відбій', rarity: 'rare', flavor: 'Найкраще слово ночі.' },
  { id: 6, title: 'Нічна зміна', rarity: 'common', flavor: 'Спотери, що не сплять, щоб ти міг заснути.' },
  { id: 7, title: 'Купол', rarity: 'legendary', flavor: 'Невидимий, але ти знаєш, що він над тобою.' },
  { id: 8, title: 'Мобільна група', rarity: 'rare', flavor: 'Прожектор і кулемет проти дрона в темряві.' },
  { id: 9, title: 'Ешелон', rarity: 'common', flavor: 'Коли їх «10х» і треба рахувати кожен.' },
  { id: 10, title: 'Чисте небо', rarity: 'legendary', flavor: 'Рідкісна картка. Як і сам спокійний ранок.' },
]

const BY_ID = new Map(CARDS.map((c) => [c.id, c]))
export const cardById = (id: number): CardDef | undefined => BY_ID.get(id)

/** Full visual token set per rarity, lifted from the Claude Design "Collectible
 * Cards" mock: `rc` the rarity accent (drives glyph + dot), plus the frame
 * border/tint/glow, card background gradient, glyph-plate fade end, top-rule
 * opacity, and the Ukrainian label. */
export interface RarityStyle {
  rc: string
  border: string
  tint: string
  glow: string
  cardBg: string
  plateEnd: string
  topOpacity: number
  label: string
}

export const RARITY_STYLE: Record<Rarity, RarityStyle> = {
  common: {
    rc: '#94a3b8',
    border: 'rgba(148,163,184,.16)',
    tint: 'rgba(148,163,184,.06)',
    glow: 'rgba(148,163,184,.12)',
    cardBg: 'linear-gradient(180deg,#0e131a,#0a0d12)',
    plateEnd: '#080b0f',
    topOpacity: 0.65,
    label: 'Звичайна',
  },
  rare: {
    rc: '#22d3ee',
    border: 'rgba(34,211,238,.35)',
    tint: 'rgba(34,211,238,.09)',
    glow: 'rgba(34,211,238,.28)',
    cardBg: 'linear-gradient(180deg,#08161a,#060d10)',
    plateEnd: '#050b0e',
    topOpacity: 0.75,
    label: 'Рідкісна',
  },
  legendary: {
    rc: '#facc15',
    border: 'rgba(250,204,21,.4)',
    tint: 'rgba(250,204,21,.1)',
    glow: 'rgba(250,204,21,.32)',
    cardBg: 'linear-gradient(180deg,#131007,#0b0905)',
    plateEnd: '#080604',
    topOpacity: 0.8,
    label: 'Легендарна',
  },
}

const ANALYSABLE_TYPES = new Set(['shahed', 'jet_drone', 'missile', 'ballistic'])

/** A target older than this since last seen is stale — no longer analysable.
 * Mirrors backend app/domain/cards.STALE_AFTER (12h). */
const STALE_MS = 12 * 60 * 60 * 1000

/** Last-seen time of a track: its most recent event, else when it was created. */
function lastSeenMs(threat: Threat): number {
  let t = Date.parse(threat.created_at)
  for (const ev of threat.events) {
    const e = Date.parse(ev.event_time)
    if (!Number.isNaN(e) && e > t) t = e
  }
  return t
}

/** A real localized weapon target — the only kind the mechanic ever engages
 * (excludes city-wide banners and unclassified rows). */
export function isAnalysableTarget(threat: Threat): boolean {
  return threat.scope === 'district' && ANALYSABLE_TYPES.has(threat.target_type)
}

/** True once a target hasn't been seen for over 12h — its debris is "stale". */
export function isStale(threat: Threat): boolean {
  return Date.now() - lastSeenMs(threat) > STALE_MS
}

/** Which analysis (if any) the current lifecycle state of a target offers —
 * mirrors backend app/domain/cards.eligible_kind_for so the button never
 * appears for something the server would reject. A live target (unconfirmed /
 * tracking) offers 'track'; a target that's off the board — shot down, lost, or
 * already impacted — offers 'remains' (analyse the debris). Stale (>12h) and
 * dismissed → none (a stale target shows an inert "stale debris" label instead,
 * see AnalyzeButton). */
export function analysisKindFor(threat: Threat): AnalysisKind | null {
  if (!isAnalysableTarget(threat)) return null
  if (isStale(threat)) return null
  if (threat.status === 'unconfirmed' || threat.status === 'tracking') return 'track'
  if (threat.status === 'destroyed' || threat.status === 'lost' || threat.status === 'impact')
    return 'remains'
  return null
}
