import CardGrid from './CardGrid'
import CompleteSeal from './CompleteSeal'
import { RARITY_RGB, RARITY_STYLE, type CardDef, type Rarity } from '@/lib/cards'

import { copiesLabel, sectionId } from './sections'

const TAGLINE: Record<Rarity, string> = {
  common: 'Основа колоди',
  rare: 'Трапляються не щоночі',
  legendary: 'Один шанс на десятки аналізів',
  epic: 'Майже міф',
  eternal: 'Одна на всю війну',
}

/** One rarity's panel of the collection: a lit header in the rarity's own
 * accent, its unlock progress as a hairline, then the grid. */
export default function RaritySection({
  rarity,
  cards,
  counts,
  newIds,
  onSelect,
}: {
  rarity: Rarity
  cards: CardDef[]
  counts: Map<number, number>
  newIds?: Set<number>
  onSelect: (card: CardDef) => void
}) {
  const { rc, plural } = RARITY_STYLE[rarity]
  const rgb = RARITY_RGB[rarity]
  const have = cards.filter((c) => counts.has(c.id)).length
  const copies = cards.reduce((n, c) => n + (counts.get(c.id) ?? 0), 0)
  const complete = have === cards.length

  return (
    <section
      id={sectionId(rarity)}
      // On a phone the panel bleeds almost to the screen edge (`-mx-3`) and keeps
      // a slim inner gutter, so the two-column cards get the same width they
      // had before the panels existed instead of paying for both paddings.
      className="relative -mx-3 mt-5 overflow-hidden rounded-[22px] border px-3 pb-3 pt-4 first:mt-1 sm:mx-0 sm:rounded-3xl sm:p-5"
      // A finished rarity is lit from the inside: stronger frame, deeper tint,
      // a glow that spills past the panel — it has to read from across the
      // room, not from a chip.
      style={{
        borderColor: `rgba(${rgb}, ${complete ? 0.45 : 0.14})`,
        background: `linear-gradient(180deg, rgba(${rgb}, ${complete ? 0.12 : 0.05}), rgba(${rgb}, 0.015) 40%, transparent)`,
        boxShadow: complete ? `0 0 60px -24px rgba(${rgb}, 0.75), inset 0 1px 0 rgba(${rgb}, 0.25)` : undefined,
      }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-56"
        style={{
          background: `radial-gradient(640px 200px at 8% 0%, rgba(${rgb}, ${complete ? 0.22 : 0.12}), transparent 70%)`,
        }}
      />

      <header className="relative flex items-end gap-4 pb-3">
        <div className="min-w-0 flex-1 pb-1">
          <span
            className="flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.24em]"
            style={{ color: rc }}
          >
            <i className="h-1.5 w-1.5 rounded-full" style={{ background: rc, boxShadow: `0 0 8px ${rc}` }} />
            {TAGLINE[rarity]}
          </span>
          <h2
            className="font-display text-2xl font-bold text-slate-100"
            style={{ textShadow: `0 0 28px rgba(${rgb}, ${complete ? 0.75 : 0.4})` }}
          >
            {plural}
          </h2>
        </div>
        {complete ? (
          <CompleteSeal rarity={rarity} total={cards.length} copies={copiesLabel(copies)} />
        ) : (
          <div className="pb-1 text-right font-mono text-[11.5px] tracking-[0.08em]">
            <div className="text-slate-100">
              <span style={{ color: rc }}>{have}</span>
              <span className="text-slate-500">/{cards.length}</span>
            </div>
            <div className="mt-1 text-slate-500">{copiesLabel(copies)}</div>
          </div>
        )}
      </header>

      <div className="relative h-px w-full bg-white/[0.06]">
        <i
          className={`absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ${
            complete ? 'section-line-complete' : ''
          }`}
          style={{
            width: `${(have / cards.length) * 100}%`,
            background: complete
              ? `linear-gradient(90deg, rgba(${rgb}, 0.35), #fff, ${rc}, rgba(${rgb}, 0.35))`
              : `linear-gradient(90deg, ${rc}, rgba(${rgb}, 0.25))`,
            boxShadow: `0 0 ${complete ? 14 : 10}px rgba(${rgb}, ${complete ? 0.8 : 0.55})`,
          }}
        />
      </div>

      <CardGrid cards={cards} counts={counts} newIds={newIds} onSelect={onSelect} />
    </section>
  )
}
