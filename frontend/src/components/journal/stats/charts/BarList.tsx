export interface BarRow {
  key: string;
  label: string;
  value: number;
  /** Secondary, already-formatted number for the trailing column (e.g. raw
   * sightings). Formatted by the caller, since only it knows the unit. */
  detail?: string;
}

interface Props {
  rows: BarRow[];
  format: (value: number) => string;
  color?: string;
}

const PHOSPHOR = "#22d3ee";

/** Horizontal bars for a ranked list — one hue, value in its own column. Goes
 * horizontal because the labels are long place names.
 *
 * Four fixed columns, and that is the point: the numbers used to sit INSIDE the
 * bar's flex track, so a wide value ("16 дн.") ate the track's width — every row
 * ended up with a different pixel width for the same 100%, and the top rows
 * wrapped their value onto a second line. The track now flexes alone. */
export default function BarList({ rows, format, color = PHOSPHOR }: Props) {
  const max = rows.reduce((n, r) => Math.max(n, r.value), 0);
  // Reserved for the whole list, not per row: a row without a detail must still
  // line its bar up with the others.
  const hasDetail = rows.some((r) => r.detail);
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((r) => (
        <li key={r.key} className="flex items-center gap-2.5">
          <span
            className="w-24 flex-none truncate text-xs text-slate-400 sm:w-28"
            title={r.label}
          >
            {r.label}
          </span>
          <span className="min-w-0 flex-1">
            <span
              className="block h-2 rounded-r-[3px]"
              style={{
                width: max ? `${Math.max((r.value / max) * 100, 2)}%` : "0%",
                background: color,
              }}
            />
          </span>
          <span className="w-14 flex-none whitespace-nowrap text-right font-mono text-xs tabular-nums text-slate-200">
            {format(r.value)}
          </span>
          {hasDetail && (
            <span className="w-20 flex-none whitespace-nowrap text-right font-mono text-[11px] tabular-nums text-slate-500">
              {r.detail}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
