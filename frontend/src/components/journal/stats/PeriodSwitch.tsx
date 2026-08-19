import { useTranslation } from "react-i18next";

import type { AnalyticsPeriod } from "@/types";

import { PERIODS } from "./statsMath";

/** The one filter row for the whole tab — every chart below re-renders against
 * the same slice, so there are no per-chart filters. */
export default function PeriodSwitch({
  value,
  onChange,
  disabled,
}: {
  value: AnalyticsPeriod;
  onChange: (period: AnalyticsPeriod) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t("journal.stats.period")}
      // Full width on a phone: three short chips floated left next to a wrapping
      // date range read as debris. On sm+ they shrink back to their own size.
      className="flex w-full gap-1 sm:w-auto"
    >
      {PERIODS.map((period) => (
        <button
          key={period}
          onClick={() => onChange(period)}
          disabled={disabled}
          aria-pressed={period === value}
          className={`flex-1 whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 sm:flex-none ${
            period === value
              ? "bg-phosphor/15 text-phosphor-soft"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {t(`journal.stats.periods.${period}`)}
        </button>
      ))}
    </div>
  );
}
