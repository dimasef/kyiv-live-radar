import { Check, ChevronDown } from 'lucide-react'
import { useState } from 'react'

export interface MultiOption<T extends string | number> {
  value: T
  label: string
  /** Shown greyed with a note — an option that exists but has nothing behind it. */
  muted?: boolean
}

/** Checkbox dropdown for a filter that takes SEVERAL values.
 *
 * The empty selection is the off position and reads as «усі» — the filter bar
 * has no separate "all" entry to pick, because an "all" that can be combined
 * with two named values is a contradiction the reader has to resolve.
 */
export default function FilterMultiSelect<T extends string | number>({
  options,
  value,
  allLabel,
  noneLabel,
  onChange,
}: {
  options: MultiOption<T>[]
  value: T[]
  /** Shown when nothing is picked, e.g. «Усі джерела». */
  allLabel: string
  /** Shown when the option list itself is empty, e.g. «Немає джерел». */
  noneLabel?: string
  onChange: (next: T[]) => void
}) {
  const [open, setOpen] = useState(false)

  const picked = options.filter((o) => value.includes(o.value))
  const label =
    picked.length === 0
      ? options.length === 0 && noneLabel
        ? noneLabel
        : allLabel
      : picked.length === 1
        ? picked[0].label
        : `${picked[0].label} +${picked.length - 1}`

  const toggle = (v: T) =>
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])

  return (
    <div className="relative">
      {/* A click anywhere else closes the list. A backdrop rather than a
          document listener: no effect to register, and the click that dismisses
          never also lands on whatever was underneath. */}
      {open && (
        <div className="fixed inset-0 z-20 cursor-default" onClick={() => setOpen(false)} />
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={`flex max-w-[16rem] items-center gap-1 rounded-lg border px-2 py-1.5 text-xs font-medium transition-colors ${
          picked.length > 0
            ? 'border-phosphor/30 bg-phosphor/10 text-phosphor-soft'
            : 'border-white/[0.08] bg-white/[0.03] text-slate-300'
        }`}
      >
        <span className="truncate">{label}</span>
        <ChevronDown size={12} className="flex-none opacity-60" />
      </button>

      {open && (
        <div className="absolute left-0 z-30 mt-1 max-h-72 min-w-[14rem] overflow-y-auto rounded-lg border border-white/10 bg-ink-900 p-1 shadow-2xl">
          {options.length === 0 && (
            <p className="px-2 py-1.5 text-[11px] text-slate-600">{noneLabel ?? '—'}</p>
          )}
          {options.map((opt) => {
            const on = value.includes(opt.value)
            return (
              <button
                key={String(opt.value)}
                type="button"
                role="checkbox"
                aria-checked={on}
                onClick={() => toggle(opt.value)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-white/[0.06] ${
                  opt.muted ? 'text-slate-500' : 'text-slate-200'
                }`}
              >
                <span
                  className={`flex h-3.5 w-3.5 flex-none items-center justify-center rounded border ${
                    on ? 'border-phosphor bg-phosphor/25 text-phosphor-soft' : 'border-white/20'
                  }`}
                >
                  {on && <Check size={10} strokeWidth={3} />}
                </span>
                <span className="truncate">{opt.label}</span>
              </button>
            )
          })}
          {value.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="mt-1 w-full rounded-md px-2 py-1.5 text-left text-[11px] text-slate-400 hover:bg-white/[0.06]"
            >
              Очистити
            </button>
          )}
        </div>
      )}
    </div>
  )
}
