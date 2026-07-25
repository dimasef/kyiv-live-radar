import type { ReprocessResult } from '@/api'

/** Before/after diff of a reprocess: header totals plus the per-day target
 * counts, showing only days whose target count changed (where phantom-count
 * inflation like the 23.07 "432 цілі" gets corrected). */
export default function ReprocessDiff({ result }: { result: ReprocessResult }) {
  const { before, after } = result
  const afterByDate = new Map(after.days.map((d) => [d.date, d.target_count]))
  const changed = before.days
    .map((d) => ({ date: d.date, before: d.target_count, after: afterByDate.get(d.date) ?? 0 }))
    .filter((r) => r.before !== r.after)

  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs">
      <div className="mb-2 font-semibold text-slate-200">Готово</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-slate-400">
        <Delta label="Треків" before={before.tracks} after={after.tracks} />
        <Delta label="Подій" before={before.events} after={after.events} />
        <Delta label="Атак" before={before.incidents} after={after.incidents} />
      </div>

      {changed.length > 0 ? (
        <table className="mt-3 w-full text-left tabular-nums">
          <thead className="text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="py-1 font-medium">Дата</th>
              <th className="py-1 font-medium">Цілі (було → стало)</th>
            </tr>
          </thead>
          <tbody>
            {changed.map((r) => (
              <tr key={r.date} className="border-t border-white/[0.05]">
                <td className="py-1 font-mono text-slate-300">{r.date}</td>
                <td className="py-1 font-mono">
                  <span className="text-slate-500">{r.before}</span>
                  <span className="mx-1 text-slate-600">→</span>
                  <span className="text-phosphor-soft">{r.after}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-2 text-slate-500">Денні лічильники цілей не змінились.</p>
      )}
    </div>
  )
}

function Delta({ label, before, after }: { label: string; before: number; after: number }) {
  return (
    <span>
      {label}: <span className="font-mono text-slate-500">{before}</span>
      <span className="mx-1 text-slate-600">→</span>
      <span className="font-mono text-slate-200">{after}</span>
    </span>
  )
}
