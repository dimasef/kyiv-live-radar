import type { AnalysisKind } from '@/api'
import { lastSeenMs } from '@/lib/threatFreshness'
import type { Threat } from '@/types'

/** Rarity drives BOTH the card-frame tint and the drop odds: rarer cards drop
 * less often. The weights live on the backend (app/domain/cards.RARITY_WEIGHT +
 * CARD_RARITY), which must mirror the `rarity` set here — this catalog stays the
 * source of truth for each card's rarity. */
export type Rarity = 'common' | 'rare' | 'legendary' | 'epic' | 'eternal'

/** Rarity tiers in ascending order — the order the collection-page tabs use. */
export const RARITIES: Rarity[] = ['common', 'rare', 'legendary', 'epic', 'eternal']

export interface CardDef {
  id: number
  title: string
  flavor: string
  rarity: Rarity
}

/** The collectible deck (from the Claude Design "Collectible Cards" v3 mock).
 * `id` MUST stay 1..N contiguous and in sync with the backend's CARD_COUNT
 * (app/domain/cards.py) — the server only stores the id. Cards are laid out in
 * ascending rarity, and `id` equals the card's display № on the collection page
 * (common 1–15, rare 16–23, legendary 24–28, epic 29–31, eternal 32). The
 * per-card glyph plate lives in cardGlyphs.ts, keyed by id. Rarity per id MUST
 * match the backend CARD_RARITY (drop weighting). Content is Ukrainian by
 * design. */
export const CARDS: CardDef[] = [
  { id: 1, rarity: 'common', title: "Тінь у небі", flavor: "Силует «шахеда» на тлі зірок. Чути — значить ще летить." },
  { id: 2, rarity: 'common', title: "Уламки", flavor: "Іноді уламки небезпечніші за цілі вироби." },
  { id: 3, rarity: 'common', title: "Відбій", flavor: "Найкраще слово ночі." },
  { id: 4, rarity: 'common', title: "Нічна зміна", flavor: "Спотери, що не сплять, щоб ти міг заснути." },
  { id: 5, rarity: 'common', title: "Сирена", flavor: "Звук, від якого прокидається все місто." },
  { id: 6, rarity: 'common', title: "Дорозвідка", flavor: "Ще раз перевірити небо, перш ніж видихнути." },
  { id: 7, rarity: 'common', title: "Гучно", flavor: "Коли чути навіть крізь навушники й закриті вікна." },
  { id: 8, rarity: 'common', title: "2 стіни", flavor: "Правило, яке рятує життя під час обстрілу." },
  { id: 9, rarity: 'common', title: "Пункт незламності", flavor: "Світло, тепло і чай, коли місто без струму." },
  { id: 10, rarity: 'common', title: "Фальш ціль", flavor: "Летить гучно, а всередині — порожньо." },
  { id: 11, rarity: 'common', title: "Каб", flavor: "Сподіваюсь до нас таке не долетить." },
  { id: 12, rarity: 'common', title: "Реактивний", flavor: "Воно як звичайне але трошки швидше." },
  { id: 13, rarity: 'common', title: "Укриття", flavor: "Сьогодні знов не ночуємо вдома?" },
  { id: 14, rarity: 'common', title: "Міг у повітрі", flavor: "Щоб тебе підняло да гепнуло!" },
  { id: 15, rarity: 'common', title: "Конус Маха", flavor: "Летить і бахає, летить і багає." },
  { id: 16, rarity: 'rare', title: "Робота ППО", flavor: "Те, на що ми покладаємо надії." },
  { id: 17, rarity: 'rare', title: "Мобільна група", flavor: "Прожектор і кулемет проти дрона в темряві." },
  { id: 18, rarity: 'rare', title: "Ешелон", flavor: "Коли їх «10х» і треба рахувати кожен." },
  { id: 19, rarity: 'rare', title: "Байрактар", flavor: "Найкращий пастух баранячих отар." },
  { id: 20, rarity: 'rare', title: "Бавовна", flavor: "Коли «десь щось» — а насправді все за планом." },
  { id: 21, rarity: 'rare', title: "НПЗ", flavor: "Мені нравицця дивиться як воно горить." },
  { id: 22, rarity: 'rare', title: "Wildberries", flavor: "Це лише ягідки..." },
  { id: 23, rarity: 'rare', title: "Хаймарс", flavor: "Дайте два!" },
  { id: 24, rarity: 'legendary', title: "Крейсер Москва", flavor: "Сдавайтесь это русский военный корабль." },
  { id: 25, rarity: 'legendary', title: "Ще 2-3 неділі", flavor: "Чесно? Да, Чесно!!!" },
  { id: 26, rarity: 'legendary', title: "Карта для нападу", flavor: "«А я сейчас вам покажу, откуда на Беларусь готовилось нападение»." },
  { id: 27, rarity: 'legendary', title: "Ізраїль за нас", flavor: "Треба допомагати Україні, а ви тільки пи*дите." },
  { id: 28, rarity: 'legendary', title: "Народний Спутник", flavor: "Ай сіі юю." },
  { id: 29, rarity: 'epic', title: "Чорнобаївка", flavor: "Місце, звідки ворожа техніка вже не повертається." },
  { id: 30, rarity: 'epic', title: "Павутина", flavor: "Коли до павучка потрапили великі метелики." },
  { id: 31, rarity: 'epic', title: "Київ за 3 дня", flavor: "Не кажи гоп, поки не перескочиш." },
  { id: 32, rarity: 'eternal', title: "Кінець Війни", flavor: "Коли звичайний день перетвориться в найкращий день в житті." },
]

const BY_ID = new Map(CARDS.map((c) => [c.id, c]))
export const cardById = (id: number): CardDef | undefined => BY_ID.get(id)

/** Visual tokens per rarity, lifted from the mock: `rc` the accent (drives the
 * glyph + dot via CSS vars), plus the frame border/tint/glow, card background
 * gradient, top-rule opacity, and the Ukrainian label. */
export interface RarityStyle {
  rc: string
  border: string
  tint: string
  glow: string
  cardBg: string
  topOpacity: number
  /** Singular label (on the card pill). */
  label: string
  /** Plural label (for the collection-page filter tabs). */
  plural: string
}

export const RARITY_STYLE: Record<Rarity, RarityStyle> = {
  common: {
    rc: '#94a3b8', border: 'rgba(148,163,184,.16)', tint: 'rgba(148,163,184,.06)',
    glow: 'rgba(148,163,184,.12)', cardBg: 'linear-gradient(180deg,#0e131a,#0a0d12)',
    topOpacity: 0.65, label: 'Звичайна', plural: 'Звичайні',
  },
  rare: {
    rc: '#22d3ee', border: 'rgba(34,211,238,.35)', tint: 'rgba(34,211,238,.09)',
    glow: 'rgba(34,211,238,.28)', cardBg: 'linear-gradient(180deg,#08161a,#060d10)',
    topOpacity: 0.75, label: 'Рідкісна', plural: 'Рідкісні',
  },
  legendary: {
    rc: '#facc15', border: 'rgba(250,204,21,.4)', tint: 'rgba(250,204,21,.1)',
    glow: 'rgba(250,204,21,.32)', cardBg: 'linear-gradient(180deg,#131007,#0b0905)',
    topOpacity: 0.8, label: 'Легендарна', plural: 'Легендарні',
  },
  epic: {
    rc: '#a855f7', border: 'rgba(168,85,247,.38)', tint: 'rgba(168,85,247,.1)',
    glow: 'rgba(168,85,247,.3)', cardBg: 'linear-gradient(180deg,#150b1e,#0b0710)',
    topOpacity: 0.82, label: 'Епічна', plural: 'Епічні',
  },
  eternal: {
    rc: '#ef4444', border: 'rgba(239,68,68,.42)', tint: 'rgba(239,68,68,.1)',
    glow: 'rgba(239,68,68,.35)', cardBg: 'linear-gradient(180deg,#1a0908,#0d0605)',
    topOpacity: 0.9, label: 'Вічна', plural: 'Вічні',
  },
}

/** The rarity accent as an "r, g, b" triplet, so callers can build `rgba(...)`
 * at any alpha (the locked "Не відкрито" frame tints itself in the slot's
 * rarity — see LockedCard). Derived once from each rarity's `rc` hex. */
export const RARITY_RGB: Record<Rarity, string> = Object.fromEntries(
  RARITIES.map((r) => {
    const h = RARITY_STYLE[r].rc.replace('#', '')
    const n = parseInt(h, 16)
    return [r, `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`]
  }),
) as Record<Rarity, string>

// --- Collection helpers (pure; shared by the collection page + account card) ---

/** A card the user owns, with how many copies. */
export interface OwnedCard {
  card_id: number
  count: number
}

/** card_id → owned copies, from a (possibly null) collection payload. */
export function collectionCounts(cards: OwnedCard[] | null | undefined): Map<number, number> {
  return new Map((cards ?? []).map((c) => [c.card_id, c.count]))
}

/** Owned-vs-total per rarity, for progress readouts and filter-tab badges. */
export function rarityBreakdown(
  owned: Map<number, number>,
): Record<Rarity, { have: number; total: number }> {
  const out = {} as Record<Rarity, { have: number; total: number }>
  for (const r of RARITIES) {
    const inR = CARDS.filter((c) => c.rarity === r)
    out[r] = { have: inR.filter((c) => owned.has(c.id)).length, total: inR.length }
  }
  return out
}

const ANALYSABLE_TYPES = new Set(['shahed', 'jet_drone', 'missile', 'ballistic'])

/** A target older than this since last seen is stale — no longer analysable.
 * Mirrors backend app/domain/cards.STALE_AFTER (12h). */
const STALE_MS = 12 * 60 * 60 * 1000

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
