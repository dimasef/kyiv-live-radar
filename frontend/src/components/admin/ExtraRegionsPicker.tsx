import { useRadar } from '@/store'
import type { Region } from '@/types'

/** Which OTHER regions a channel may localize into, beyond its primary.
 *
 * A source never pins a place outside its bindings, so this is what lets a Kyiv
 * channel keep reporting the northern approach. The primary is excluded — it is
 * always bound, and offering it as a toggle would imply it can be turned off.
 */
export default function ExtraRegionsPicker({
  primary,
  value,
  onChange,
}: {
  primary: Region
  value: Region[]
  onChange: (next: Region[]) => void
}) {
  const regions = useRadar((s) => s.regions)
  const others = regions.filter((r) => r.id !== primary)

  return (
    <div className="flex flex-wrap gap-1">
      {others.map((region) => {
        const on = value.includes(region.id)
        return (
          <button
            key={region.id}
            type="button"
            aria-pressed={on}
            onClick={() =>
              onChange(on ? value.filter((r) => r !== region.id) : [...value, region.id])
            }
            className={`rounded-md border px-2 py-1 text-[11px] transition-colors duration-200 ${
              on
                ? 'border-phosphor/30 bg-phosphor/15 text-phosphor-soft'
                : 'border-white/10 bg-white/[0.03] text-slate-400'
            } ${region.active ? '' : 'opacity-60'}`}
          >
            {region.name_uk}
          </button>
        )
      })}
      {others.length === 0 && <span className="text-[11px] text-slate-600">—</span>}
    </div>
  )
}
