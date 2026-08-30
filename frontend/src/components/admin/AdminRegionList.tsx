import { useRadar } from '@/store'
import type { Region } from '@/types'

import { groupByRegion } from './regionGroups'

/** A management list split into per-region blocks.
 *
 * The four lists on «Керування» are the operator's live inventory, and until
 * now they were one flat pile across four oblasts: during a raid on two of
 * them, deciding which «Ціль T2831» to cancel meant opening each one. The
 * heading is the region, exactly as the Sources tab groups channels.
 *
 * A single-region list (the common case — one oblast is active at a time) still
 * gets its heading: which oblast the targets are over is the thing being
 * grouped, and hiding it when the answer is "all of them, one region" would
 * make the layout jump the moment a second region shows up.
 */
export default function AdminRegionList<T>({
  items,
  regionOf,
  children,
}: {
  items: T[]
  regionOf: (item: T) => Region | string
  /** Renders ONE row, `<li>` and key included — the rows already own their
   * markup, and wrapping them here would nest a second list item. */
  children: (item: T) => React.ReactNode
}) {
  const catalogue = useRadar((s) => s.regions)
  const buckets = groupByRegion(items, catalogue, regionOf)

  return (
    <div className="space-y-2.5">
      {buckets.map((bucket, i) => (
        <div key={bucket.region?.id ?? `orphans-${i}`}>
          {bucket.region && (
            <p className="mb-1 text-[11px] font-medium text-slate-500">
              {bucket.region.name_uk}
              <span className="ml-1.5 text-slate-600">{bucket.items.length}</span>
            </p>
          )}
          <ul className="space-y-1.5">{bucket.items.map(children)}</ul>
        </div>
      ))}
    </div>
  )
}
