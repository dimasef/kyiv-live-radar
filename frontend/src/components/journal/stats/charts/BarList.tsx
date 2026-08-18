export interface BarRow {
  key: string
  label: string
  value: number
  /** Secondary number shown next to the value (e.g. raw sightings). */
  detail?: string
}

interface Props {
  rows: BarRow[]
  format: (value: number) => string
  color?: string
}

const PHOSPHOR = '#22d3ee'

/** Horizontal bars for a ranked list — one hue, value labeled at the tip. Goes
 * horizontal because the labels are long place names. */
export default function BarList({ rows, format, color = PHOSPHOR }: Props) {
  const max = rows.reduce((n, r) => Math.max(n, r.value), 0)
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((r) => (
        <li key={r.key} className="flex items-center gap-2.5">
          <span className="w-28 flex-none truncate text-[11px] text-slate-400" title={r.label}>
            {r.label}
          </span>
          <span className="flex min-w-0 flex-1 items-center gap-2">
            <span
              className="h-2 rounded-r-[3px]"
              style={{
                width: max ? `${Math.max((r.value / max) * 100, 2)}%` : '0%',
                background: color,
              }}
            />
            <span className="font-mono text-[11px] tabular-nums text-slate-200">
              {format(r.value)}
            </span>
            {r.detail && (
              <span className="font-mono text-[10px] tabular-nums text-slate-600">{r.detail}</span>
            )}
          </span>
        </li>
      ))}
    </ul>
  )
}
