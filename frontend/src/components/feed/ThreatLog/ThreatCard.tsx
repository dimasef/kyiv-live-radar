import { Sparkles, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useRadar } from "@/store";
import { threatColor } from "@/theme";
import { CountBadge } from "@/threatDisplay";
import { typeLabel } from "@/threatState";
import type { FeedEntry } from "@/types";

import { DevId, DevSource, EventTime, SourceName } from "./badges";
import ClampText from "./ClampText";
import SightingDistance from "./SightingDistance";
import StatusChip from "./StatusChip";
import TypeGlyph from "./TypeGlyph";

/** One live sighting — the feed's main card. Click toggles map inspection. */
export default function ThreatCard({ event, threat }: FeedEntry) {
  const { t } = useTranslation();
  const isSelected = useRadar((s) => s.inspectedThreat?.id === threat.id);
  const inspectThreat = useRadar((s) => s.inspectThreat);
  const clearInspection = useRadar((s) => s.clearInspection);

  const color = threatColor(threat);
  const toggleInspect = () => (isSelected ? clearInspection() : inspectThreat(threat));
  const rescued = event.decision_source === "triage";

  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        aria-pressed={isSelected}
        onClick={toggleInspect}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleInspect();
          }
        }}
        className={`feed-item cursor-pointer rounded-lg border px-2.5 py-2 text-xs transition-colors duration-200 ${
          isSelected
            ? "border-white/20 bg-white/[0.09]"
            : "border-white/[0.05] bg-white/[0.03] hover:bg-white/[0.06]"
        }`}
        style={{
          borderLeft: `2px solid ${color}`,
          boxShadow: isSelected
            ? `inset 2px 0 8px -4px ${color}55, 0 0 0 1px ${color}55`
            : `inset 2px 0 8px -4px ${color}55`,
        }}
      >
        <div className="flex items-baseline justify-between gap-2">
          <span className="flex min-w-0 flex-wrap items-center gap-1.5 font-medium text-slate-100">
            <TypeGlyph threat={threat} />
            <StatusChip threat={threat} />
            {typeLabel(threat, t)}
            <CountBadge
              count={event.event_target_count ?? threat.target_count}
              className="ml-1 font-mono font-semibold text-amber-400"
            />
            <SightingDistance event={event} className="ml-0.5 flex-none text-[10px]" />
          </span>
          <span className="flex items-center gap-1.5">
            {rescued && (
              <span className="flex items-center gap-1 rounded bg-white/[0.06] px-1 py-px text-[9px] font-medium text-slate-400">
                <Sparkles size={9} className="flex-none" />
                {t("log.rescued")}
              </span>
            )}
            <DevId>
              T{threat.id}/M{event.id}
            </DevId>
            <DevSource source={event.decision_source} />
            <EventTime iso={event.event_time} />
          </span>
        </div>
        <ClampText
          text={event.raw_text}
          className="mt-0.5 break-words leading-snug text-slate-300"
        />
        <SourceName name={event.source_name} />

        {threat.has_conflict && (
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="flex items-center gap-1 text-[10px] font-medium text-orange-400">
              <TriangleAlert size={10} className="flex-none" />
              {t("log.conflict")}
            </span>
          </div>
        )}
      </div>
    </li>
  );
}
