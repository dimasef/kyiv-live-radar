import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { TYPE_COLORS } from "@/theme";
import type { StatsDay } from "@/types";

import ColumnChart from "./charts/ColumnChart";
import { shouldGroupByWeek, trendBuckets } from "./statsMath";

/** How the target mix moves over the period: stacked columns, one per day or per
 * week depending on span. The legend lives in TypeTable below (which is also the
 * table twin), so identity is never carried by color alone. */
export default function TypeTrend({
  days,
  locale,
}: {
  days: StatsDay[];
  locale: string;
}) {
  const { t } = useTranslation();
  const byWeek = shouldGroupByWeek(days);
  const buckets = useMemo(
    () => trendBuckets(days, byWeek, locale),
    [days, byWeek, locale],
  );

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="panel-title">{t("journal.stats.trend")}</span>
        <span className="text-[10px] uppercase tracking-[0.12em] text-slate-600">
          {byWeek ? t("journal.stats.perWeek") : t("journal.stats.perDay")}
        </span>
      </div>
      <ColumnChart
        columns={buckets.map((b) => ({
          key: b.key,
          label: b.label,
          value: b.segments.reduce((n, s) => n + s.count, 0),
          segments: b.segments.map((s) => ({
            key: s.type,
            label: t(`target.${s.type}`),
            value: s.count,
            color: TYPE_COLORS[s.type],
          })),
        }))}
        format={(v) => String(v)}
        tickEvery={byWeek ? 2 : Math.ceil(buckets.length / 8)}
        heightClass="h-32"
        tableLabel={t("journal.stats.trend")}
        valueHeader={t("journal.targets")}
      />
    </div>
  );
}
