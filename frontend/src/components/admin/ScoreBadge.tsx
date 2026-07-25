import type { SourceStats } from '@/api'

import { scoreBreakdown, scoreColor } from './sourceFormat'

/** The quality score, with a hover tooltip that shows exactly how it's computed:
 * each component's goodness × its (renormalized) weight = the points it adds,
 * summing to the total. */
export default function ScoreBadge({ stats }: { stats: SourceStats }) {
  const score = stats.quality_score
  const parts = scoreBreakdown(stats)

  return (
    <span className="group relative inline-flex cursor-help items-center gap-1">
      <span className={`font-mono text-sm font-bold ${scoreColor(score)}`}>
        {score == null ? '—' : score}
      </span>
      <span className="text-[10px] text-slate-500">score</span>
      {parts.length > 0 && (
        <div className="pointer-events-none absolute left-0 top-full z-50 mt-1 hidden w-64 rounded-lg border border-white/10 bg-ink-900 p-2.5 text-[11px] shadow-2xl group-hover:block">
          <div className="mb-1.5 font-semibold text-slate-200">Як рахується score</div>
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-[10px] text-slate-600">
                <th className="text-left font-normal">компонент</th>
                <th className="text-right font-normal">знач.</th>
                <th className="pl-2 text-right font-normal">вага</th>
                <th className="pl-2 text-right font-normal">бали</th>
              </tr>
            </thead>
            <tbody>
              {parts.map((p) => (
                <tr key={p.label} className="text-slate-400">
                  <td className="py-0.5">{p.label}</td>
                  <td className="text-right tabular-nums">{Math.round(p.goodness * 100)}%</td>
                  <td className="pl-2 text-right tabular-nums text-slate-500">{Math.round(p.weightPct)}%</td>
                  <td className="pl-2 text-right tabular-nums text-phosphor-soft">+{p.points.toFixed(1)}</td>
                </tr>
              ))}
              <tr className="border-t border-white/10 font-semibold text-slate-200">
                <td className="pt-1" colSpan={3}>
                  Разом
                </td>
                <td className="pt-1 text-right tabular-nums">{score}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </span>
  )
}
