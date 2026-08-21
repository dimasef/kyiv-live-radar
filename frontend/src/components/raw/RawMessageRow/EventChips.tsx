import { useTranslation } from "react-i18next";

import { deleteEvent, deleteNotice } from "@/api";
import AdminActionButton from "@/components/admin/AdminActionButton";
import { TYPE_COLORS } from "@/theme";
import type { RawMessage, TargetType } from "@/types";

import { type NoticeSet } from "../NoticeControl";
import type { DropEvent } from "./types";

/** The T/M code chips for the ThreatEvents this message produced, each tagged
 * with the target type stamped on it (colour + label). Wraps, so a "чисто" that
 * closed a dozen tracks lays out as rows instead of overflowing the card.
 *
 * Each chip carries the one write this view allows: taking the sighting off the
 * message it was parsed from. This is where a wrong parse is actually SEEN —
 * next to the text that caused it — and sending the admin to hunt the same track
 * down on the «Керування» tab was how bad parses stayed on the map. */
export default function EventChips({
  item,
  onDropEvent,
  onSetNotice,
}: {
  item: RawMessage;
  onDropEvent: DropEvent;
  onSetNotice: NoticeSet;
}) {
  const { t } = useTranslation();
  if (item.events.length === 0 && item.notice_id == null) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {item.events.map((e) => {
        const known = e.target_type != null && e.target_type in TYPE_COLORS;
        const color = known
          ? TYPE_COLORS[e.target_type as TargetType]
          : TYPE_COLORS.unknown;
        return (
          <span
            key={e.event_id}
            className="inline-flex items-center gap-1 rounded bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
          >
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: color }}
            />
            {e.target_type && (
              <span className="text-slate-300">
                {t(`target.${e.target_type}`)}
              </span>
            )}
            {e.district_name && (
              <span className="text-slate-300">{e.district_name}</span>
            )}
            <span className="opacity-70">
              T{e.threat_id}/M{e.event_id}
            </span>
            {e.incident_id != null && (
              <span className="text-slate-500">I{e.incident_id}</span>
            )}
            {e.corroboration_count != null && (
              <span className="text-slate-500">
                {e.corroboration_count} {t("log.corroboration")}
              </span>
            )}
            {e.confidence != null && (
              <span className="text-slate-500">
                {Math.round(e.confidence * 100)}%
              </span>
            )}
            <AdminActionButton
              label="×"
              title="Зняти подію з повідомлення"
              tone="danger"
              compact
              confirm={`Зняти подію M${e.event_id} з треку T${e.threat_id}? Якщо вона в треку остання, трек буде скасовано.`}
              onRun={() =>
                deleteEvent(e.event_id).then(() =>
                  onDropEvent(item.id, e.event_id),
                )
              }
            />
          </span>
        );
      })}
      {item.notice_id != null && (
        <span className="inline-flex items-center gap-1 rounded bg-sky-400/10 px-1.5 py-0.5 font-mono text-[10px] text-sky-300/80">
          N{item.notice_id}
          {item.notice_kind && (
            <span className="opacity-70">
              {t(`notice.${item.notice_kind}`)}
            </span>
          )}
          <AdminActionButton
            label="×"
            title="Прибрати нотіс зі стрічки"
            tone="danger"
            compact
            confirm={`Прибрати нотіс N${item.notice_id} зі стрічки?`}
            onRun={() =>
              deleteNotice(item.notice_id!).then(() =>
                onSetNotice(item.id, null),
              )
            }
          />
        </span>
      )}
    </div>
  );
}
