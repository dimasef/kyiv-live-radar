import { fetchCoverageCandidates, type CoverageCandidate } from '@/api'
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
 * that «Добрянка» came up seven times in one night and is worth geocoding. */
export default function CoverageCandidates() {
  const { data: candidates, loaded } = useAsyncData<CoverageCandidate[]>(
    () => fetchCoverageCandidates(60, CANDIDATE_SCAN),
    [],
    [],
  )

  if (loaded && candidates.length === 0) return null

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
        варто геокодувати першим.
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {candidates.map((c) => (
          <CandidateChip key={c.name} candidate={c} />
        ))}
      </ul>
    </section>
  )
}

function CandidateChip({ candidate }: { candidate: CoverageCandidate }) {
  return (
    <li
      // The example message is what tells a real village from a coincidence, and
      // it is one glance away rather than a click into /raw.
      title={candidate.example_text}
      className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1"
    >
      <span className="text-xs text-slate-200">{candidate.name}</span>
      <span className="text-[10px] tabular-nums text-slate-500">{candidate.count}</span>
    </li>
  )
}
