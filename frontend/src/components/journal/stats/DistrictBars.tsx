import { useTranslation } from "react-i18next";

import type { DistrictStat } from "@/types";

import BarList from "./charts/BarList";

interface Props {
  districts: DistrictStat[];
  districtName: (id: number) => string;
  limit?: number;
}

/** Where targets keep showing up. Ranked by the number of DAYS a district saw a
 * target, not by raw sighting count: event volume tracks how talkative the
 * spotters were that night, days don't. Raw sightings ride along dimmed. */
export default function DistrictBars({
  districts,
  districtName,
  limit = 10,
}: Props) {
  const { t } = useTranslation();
  const rows = districts.slice(0, limit);
  if (!rows.length) return null;

  return (
    <div>
      <div className="panel-title mb-2.5">
        {t("journal.stats.topDistricts")}
      </div>
      <BarList
        rows={rows.map((d) => ({
          key: String(d.district_id),
          label: districtName(d.district_id),
          value: d.days,
          // Carries its own unit: a bare grey number next to "16 дн." read as an
          // unexplained second score, and the footnote that explained it is the
          // one line nobody reads.
          detail: t("journal.stats.msgCount", { n: d.events }),
        }))}
        format={(v) => t("journal.stats.dayCount", { count: v })}
      />
      <p className="mt-2.5 text-xs leading-relaxed text-slate-500">
        {t("journal.stats.districtNote")}
      </p>
    </div>
  );
}
