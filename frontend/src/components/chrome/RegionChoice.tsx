import { useRadar } from '@/store'
import type { Region } from '@/types'

/** The list of oblasts to pick from — shared by the first-run gate and the
 * settings control, so the two can never drift on what is offered or how a
 * not-yet-covered region is labelled.
 *
 * A region with no coverage yet is offerable on purpose: picking it is how the
 * reader says where they are, and it costs nothing to be right early. What it
 * cannot do yet is notify — see RegionPickerModal's note.
 */
export default function RegionChoice({
  value,
  onChange,
}: {
  value: Region | null
  onChange: (id: Region) => void
}) {
  const regions = useRadar((s) => s.regions)

  return (
    <div className="flex flex-col gap-1.5">
      {regions.map((region) => {
        const on = value === region.id
        return (
          <button
            key={region.id}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(region.id)}
            className={`flex items-center justify-between rounded-lg border px-3 py-2.5 text-left text-sm transition-colors duration-200 ${
              on
                ? 'border-phosphor/40 bg-phosphor/15 text-phosphor-soft'
                : 'border-white/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06]'
            }`}
          >
            <span className="font-medium">{region.name_uk}</span>
            {!region.active && (
              <span className="rounded border border-white/10 px-1.5 py-px text-[10px] text-slate-500">
                готується
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
