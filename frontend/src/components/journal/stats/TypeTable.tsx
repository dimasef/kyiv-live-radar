import { useTranslation } from "react-i18next";

import { TYPE_COLORS } from "@/theme";

import { formatPercent, typeRows } from "./statsMath";

/** The target-type breakdown as numbers: doubles as the legend for the trend
 * chart above and as its WCAG-clean table twin. */
export default function TypeTable({
  typeTotals,
  typeDays,
}: {
  typeTotals: Record<string, number>;
  typeDays: Record<string, number>;
}) {
  const { t } = useTranslation();
  const rows = typeRows(typeTotals, typeDays);
  if (!rows.length) return null;

  return (
    <table className="w-full text-xs">
      <caption className="panel-title mb-2 text-left">
        {t("journal.byType")}
      </caption>
      <thead>
        <tr className="text-[10px] uppercase tracking-[0.12em] text-slate-600">
          <th scope="col" className="pb-1 text-left font-normal">
            {t("journal.stats.type")}
          </th>
          <th scope="col" className="pb-1 text-right font-normal">
            {t("journal.targets")}
          </th>
          <th scope="col" className="pb-1 text-right font-normal">
            {t("journal.stats.share")}
          </th>
          <th scope="col" className="pb-1 text-right font-normal">
            {t("journal.stats.onDays")}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.type} className="border-t border-white/[0.05]">
            <th
              scope="row"
              className="py-1.5 text-left font-normal text-slate-400"
            >
              <span className="flex items-center gap-1.5">
                <span
                  className="h-2 w-2 flex-none rounded-sm"
                  style={{ background: TYPE_COLORS[r.type] }}
                />
                {t(`target.${r.type}`)}
              </span>
            </th>
            <td className="py-1.5 text-right font-mono tabular-nums text-slate-200">
              {r.count}
            </td>
            <td className="py-1.5 text-right font-mono tabular-nums text-slate-500">
              {formatPercent(r.share)}
            </td>
            <td className="py-1.5 text-right font-mono tabular-nums text-slate-500">
              {r.days}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
