import { RotateCcw, X } from 'lucide-react'
import { useState } from 'react'

import {
  dismissToponym,
  fetchCoverageCandidates,
  fetchDismissedToponyms,
  restoreToponym,
  type CoverageCandidate,
} from '@/api'
import { useAsyncData } from '@/lib/useAsyncData'

/** How deep the ranking scans. Far deeper than the message list below it: a
 * candidate's whole signal is that it REPEATS, and a window too short for a
 * village to come up twice can only ever show a flat list of ones. */
const CANDIDATE_SCAN = 4000

/** The gazetteer work-list: place-names the channels used that the parser
 * doesn't know, ranked by how often they came up.
 *
 * This is the view the whole coverage-gap queue exists for. Reading unlocalized
 * messages one by one tells you a message failed; only the ranking tells you
 * that «Добрянка» came up seven times in one night and is worth geocoding.
 *
 * Whatever is left after the word lists have had their say is a judgement call,
 * so the operator makes it here: «×» on a row that is not a place hides it for
 * good (`toponym_dismissals`), and the hidden ones stay one click from coming
 * back. */
export default function CoverageCandidates() {
  const { data: candidates, loaded } = useAsyncData<CoverageCandidate[]>(
    () => fetchCoverageCandidates(60, CANDIDATE_SCAN),
    [],
    [],
  )
  // Both mutations answer with the full list, so the panel takes the server's
  // word for it instead of refetching or patching an array by hand.
  const { data: dismissed, setData: setDismissed } = useAsyncData<string[]>(
    fetchDismissedToponyms,
    [],
    [],
  )
  const hidden = new Set(dismissed)

  const hide = async (name: string) => setDismissed(await dismissToponym(name))
  const restore = async (name: string) => setDismissed(await restoreToponym(name))

  // Hidden in place rather than refetched: the ranking is a 4000-message scan,
  // and the row the operator just judged is exactly the one they know about.
  const visible = candidates.filter((c) => !hidden.has(c.name))

  if (loaded && candidates.length === 0 && dismissed.length === 0) return null

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-medium text-slate-300">
        Кандидати в газетир{' '}
        <span className="font-normal text-slate-500">
          · {CANDIDATE_SCAN} останніх повідомлень
        </span>
      </h3>
      <p className="text-[11px] text-slate-500">
        Слова, схожі на назву місця, яких немає в газетирі — за частотою. Те, що повторюється,
        варто геокодувати першим. «×» — не прогалина, сховати назавжди.
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {visible.map((c) => (
          <CandidateChip key={c.name} candidate={c} onDismiss={hide} />
        ))}
      </ul>
      {dismissed.length > 0 && <DismissedList words={dismissed} onRestore={restore} />}
    </section>
  )
}

function CandidateChip({
  candidate,
  onDismiss,
}: {
  candidate: CoverageCandidate
  onDismiss: (name: string) => void
}) {
  return (
    <li
      // The example message is what tells a real village from a coincidence, and
      // it is one glance away rather than a click into /raw.
      title={candidate.example_text}
      className="group flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] py-1 pl-2.5 pr-1.5"
    >
      <span className="text-xs text-slate-200">{candidate.name}</span>
      <span className="text-[10px] tabular-nums text-slate-500">{candidate.count}</span>
      <button
        type="button"
        onClick={() => onDismiss(candidate.name)}
        aria-label={`Не прогалина: ${candidate.name}`}
        title="Не прогалина — сховати"
        className="rounded-full p-0.5 text-slate-600 transition-colors hover:bg-white/[0.08] hover:text-slate-300"
      >
        <X size={11} strokeWidth={2.5} />
      </button>
    </li>
  )
}

/** The words already ruled out. Folded away by default — this is a list you
 * open to undo a mistake, not one you read. */
function DismissedList({
  words,
  onRestore,
}: {
  words: string[]
  onRestore: (name: string) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="text-[11px] text-slate-500 transition-colors hover:text-slate-300"
      >
        Не прогалини · {words.length}
      </button>
      {open && (
        <ul className="mt-1.5 flex flex-wrap gap-1.5">
          {words.map((w) => (
            <li
              key={w}
              className="flex items-center gap-1.5 rounded-full border border-white/[0.06] bg-transparent py-1 pl-2.5 pr-1.5"
            >
              <span className="text-xs text-slate-500">{w}</span>
              <button
                type="button"
                onClick={() => onRestore(w)}
                aria-label={`Повернути ${w}`}
                title="Повернути до кандидатів"
                className="rounded-full p-0.5 text-slate-600 transition-colors hover:bg-white/[0.08] hover:text-slate-300"
              >
                <RotateCcw size={11} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
