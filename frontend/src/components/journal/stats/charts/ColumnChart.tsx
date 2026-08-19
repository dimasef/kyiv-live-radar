import { useState } from "react";

export interface ColumnSegment {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface Column {
  key: string;
  /** x-axis tick text; rendered for every `tickEvery`-th column. */
  label: string;
  value: number;
  /** Stacked parts, bottom-first. Omit for a single-hue column. */
  segments?: ColumnSegment[];
}

interface Props {
  columns: Column[];
  /** Single-series fill; ignored for columns that carry `segments`. */
  color?: string;
  format: (value: number) => string;
  /** Label every n-th column, so a 24- or 90-column axis stays readable. */
  tickEvery?: number;
  heightClass?: string;
  /** Screen-reader table caption — the WCAG-clean twin of the chart. */
  tableLabel: string;
  valueHeader: string;
}

const PHOSPHOR = "#22d3ee";

/** Column chart, single-hue or stacked, built from divs like the rest of this
 * page's visuals. Hover/focus drives one readout line above the plot instead of
 * a floating tooltip: it can't overflow a phone viewport, works on touch, and
 * gives keyboard users the same values. The max column keeps a direct label. */
export default function ColumnChart({
  columns,
  color = PHOSPHOR,
  format,
  tickEvery = 1,
  heightClass = "h-28",
  tableLabel,
  valueHeader,
}: Props) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const max = columns.reduce((n, c) => Math.max(n, c.value), 0);
  const peak = columns.find((c) => c.value === max && max > 0) ?? null;
  const active = columns.find((c) => c.key === activeKey) ?? peak;

  return (
    <div>
      <div className="mb-2 flex min-h-[18px] items-baseline gap-2 text-xs">
        {active && (
          <>
            <span className="text-slate-400">{active.label}</span>
            <span className="font-mono tabular-nums text-slate-100">
              {format(active.value)}
            </span>
            {active.segments?.length ? (
              <span className="flex flex-wrap gap-x-2 text-slate-500">
                {active.segments.map((s) => (
                  <span key={s.key} className="flex items-center gap-1">
                    <span
                      className="h-1.5 w-1.5 flex-none rounded-sm"
                      style={{ background: s.color }}
                    />
                    <span className="font-mono tabular-nums">{s.value}</span>
                  </span>
                ))}
              </span>
            ) : null}
          </>
        )}
      </div>

      <div
        className={`flex items-end gap-px border-b border-white/[0.08] ${heightClass}`}
        onMouseLeave={() => setActiveKey(null)}
      >
        {columns.map((c) => {
          const isActive = active?.key === c.key;
          return (
            <button
              key={c.key}
              type="button"
              onMouseEnter={() => setActiveKey(c.key)}
              onFocus={() => setActiveKey(c.key)}
              onBlur={() => setActiveKey(null)}
              aria-label={`${c.label}: ${format(c.value)}`}
              className="group relative flex h-full flex-1 items-end justify-center outline-none"
            >
              <span
                // A 2px gap in the surface color is what separates touching
                // segments — never a border drawn around them. flex-grow does the
                // proportional split, so the gaps come out of the height instead
                // of overflowing it.
                className={`flex w-full max-w-[24px] flex-col-reverse gap-[2px] rounded-t transition-opacity ${
                  isActive
                    ? "opacity-100"
                    : "opacity-80 group-hover:opacity-100"
                }`}
                style={{ height: max ? `${(c.value / max) * 100}%` : "0%" }}
              >
                {c.segments?.length ? (
                  c.segments.map((s) => (
                    <span
                      key={s.key}
                      className="w-full min-h-0 last:rounded-t"
                      style={{
                        flexGrow: s.value,
                        flexBasis: 0,
                        background: s.color,
                      }}
                    />
                  ))
                ) : (
                  <span
                    className="h-full w-full rounded-t"
                    style={{ background: color }}
                  />
                )}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-1 flex gap-px">
        {columns.map((c, i) => (
          <span
            key={c.key}
            className="flex-1 text-center font-mono text-[10px] tabular-nums text-slate-600"
          >
            {i % tickEvery === 0 ? c.label : ""}
          </span>
        ))}
      </div>

      <table className="sr-only">
        <caption>{tableLabel}</caption>
        <thead>
          <tr>
            <th scope="col">—</th>
            <th scope="col">{valueHeader}</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((c) => (
            <tr key={c.key}>
              <th scope="row">{c.label}</th>
              <td>{format(c.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
