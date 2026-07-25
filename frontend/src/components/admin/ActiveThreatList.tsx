import { useRadar } from '@/store'

import ThreatAdminRow from './ThreatAdminRow'

/** All live tracks on the map right now — the primary surface for retyping or
 * cancelling a mis-parsed target. Impacts are included (they're real strike
 * markers an admin may still want to remove if wrong). */
export default function ActiveThreatList() {
  const threats = useRadar((s) => s.threats)
  const list = Object.values(threats).sort((a, b) => b.created_at.localeCompare(a.created_at))

  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Активні цілі ({list.length})
      </h2>
      {list.length === 0 ? (
        <p className="text-xs text-slate-600">Немає активних цілей.</p>
      ) : (
        <ul className="space-y-1.5">
          {list.map((threat) => (
            <ThreatAdminRow key={threat.id} threat={threat} />
          ))}
        </ul>
      )}
    </section>
  )
}
