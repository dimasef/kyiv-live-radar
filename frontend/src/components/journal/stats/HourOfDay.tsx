import { useTranslation } from "react-i18next";

import type { HourBucket } from "@/types";

import ColumnChart from "./charts/ColumnChart";
import { formatPercent, hourLabel } from "./statsMath";

/** Hour-of-day rhythm, as two small multiples over one shared 0-23 Kyiv axis:
 * the chance of being under alert, and how many targets appear. Two charts, not
 * two y-scales on one plot — a dual axis would invent a correlation. */
export default function HourOfDay({
  hours,
  alertDaysObserved,
}: {
  hours: HourBucket[];
  alertDaysObserved: number;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-6">
      {alertDaysObserved > 0 && (
        <div>
          <div className="panel-title mb-2">
            {t("journal.stats.hourAlertShare")}
          </div>
          <ColumnChart
            columns={hours.map((h) => ({
              key: `a${h.hour}`,
              label: hourLabel(h.hour),
              value: Math.round(h.alert_share * 1000) / 10,
            }))}
            format={(v) => formatPercent(v / 100, 1)}
            tickEvery={3}
            tableLabel={t("journal.stats.hourAlertShare")}
            valueHeader={t("journal.stats.hourAlertShare")}
          />
        </div>
      )}

      <div>
        <div className="panel-title mb-2">{t("journal.stats.hourTargets")}</div>
        <ColumnChart
          columns={hours.map((h) => ({
            key: `t${h.hour}`,
            label: hourLabel(h.hour),
            value: h.target_count,
          }))}
          format={(v) => String(v)}
          tickEvery={3}
          tableLabel={t("journal.stats.hourTargets")}
          valueHeader={t("journal.targets")}
        />
      </div>

      <p className="text-xs leading-relaxed text-slate-500">
        {t("journal.stats.hourNote")}
      </p>
    </div>
  );
}
