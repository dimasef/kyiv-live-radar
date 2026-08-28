import type { ReactNode } from 'react'

import type { RegionInfo } from '@/types'

/** One region's block of source rows. The header carries the count and, for a
 * region declared but not covered yet, says so — a channel can be tagged with
 * one before its gazetteer exists, so an empty block there is expected. */
export default function SourceRegionGroup({
  region,
  count,
  children,
}: {
  region: RegionInfo
  count: number
  children: ReactNode
}) {
  return (
    <li>
      <div className="mb-1 flex items-center gap-2 px-0.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {region.name_uk}
        </span>
        <span className="font-mono text-[11px] tabular-nums text-slate-600">{count}</span>
        {!region.active && (
          <span className="rounded border border-white/10 px-1 py-px text-[10px] text-slate-500">
            готується
          </span>
        )}
      </div>
      {count === 0 ? (
        <p className="px-0.5 pb-1 text-xs text-slate-600">Каналів немає.</p>
      ) : (
        <ul className="space-y-1.5">{children}</ul>
      )}
    </li>
  )
}
