import { Clock, RadioTower } from "lucide-react";
import { useTranslation } from "react-i18next";

import { durationLabel } from "@/lib/duration";
import { useRadar } from "@/store";
import { STATUS_COLORS } from "@/theme";
import type { Notice } from "@/types";

import { alertForClear, clearTailKey } from "./allClear";
import { DevId, EventTime, SourceName } from "./badges";
import ClampText from "./ClampText";

const AC = STATUS_COLORS.clear;

/** How fast the sweep crosses and the edge breathes. Slow on purpose: this card
 * sits in a feed that is scrolled, not watched, and a quick pulse next to live
 * threat cards competes with them for the eye. */
const PULSE = "5.5s";

/** The all-clear green at `pct` opacity, as an 8-digit hex colour.
 *
 * Not `color-mix()`: every sibling card in this feed builds its tint by
 * appending hex alpha, and this app is read on old TV browsers (see
 * lib/kyivTime for the other half of that story) where an unsupported
 * `color-mix()` makes the whole declaration invalid — taking the card's
 * background, glow and ring with it rather than degrading. */
const mix = (pct: number) =>
  AC +
  Math.round((pct / 100) * 255)
    .toString(16)
    .padStart(2, "0");

/** The all-clear: the one card in this feed that is good news, and the only one
 * that says the raid is over rather than reporting another piece of it.
 *
 * It is deliberately the loudest card in the timeline — a glow, a sweep, halo
 * rings and a checkmark that draws itself. Everything else here competes to be
 * noticed during an attack; this is the entry someone scrolls back to look for
 * afterwards, and it should be findable at a glance. All of it is silenced
 * under prefers-reduced-motion (see index.css).
 */
export default function AllClearCard({ notices }: { notices: Notice[] }) {
  const { t } = useTranslation();
  const alerts = useRadar((s) => s.alerts);
  const head = notices[0];
  // A type-scoped stand-down («Відбій балістичної загрози») ends ONE kind of
  // threat while the raid runs on — it must not be announced as «Відбій
  // тривоги», and alertForClear refuses to date it for the same reason.
  const scoped = head.target_type !== "unknown";
  const closed = alertForClear(alerts, head);
  const sources = [...new Set(notices.map((n) => n.source_name).filter(Boolean))];
  // A full clear says the same thing every time, and the official channel says
  // it in the same boilerplate («❕Відбій повітряної тривоги! Просимо уважно
  // слідкувати за повідомленнями…») — byte-identical on every відбій in the
  // stored corpus. The card states it plainly instead, and does NOT offer the
  // original: an «оригінал» toggle only earns its place when the source text
  // carries something the card dropped, and here it never does. A TYPE-SCOPED
  // stand-down keeps its own words: «По балістиці відбій» is already short,
  // specific, and not what this sentence would say.
  const body = scoped
    ? head.text
    : t("notice.clearBody", {
        where: t(`notice.clearWhere.${head.region}`, head.region),
        tail: t(clearTailKey(head.id)),
      });

  return (
    <li
      className="feed-item relative overflow-hidden rounded-xl border px-3 pt-2.5 pb-2.5 text-xs"
      style={{
        // Consumed by the animation classes in index.css, so the tempo is set
        // in one place rather than repeated on each animated layer.
        ["--ac-pd" as string]: PULSE,
        borderColor: "rgba(255,255,255,.06)",
        borderLeft: `3px solid ${AC}`,
        background: `linear-gradient(103deg, ${mix(16)} 0%, ${mix(7)} 42%, rgba(255,255,255,.02) 100%)`,
        boxShadow: `inset 3px 0 18px -6px ${mix(65)}, 0 0 0 1px ${mix(12)}, 0 8px 26px -14px ${mix(80)}`,
      }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-xl" aria-hidden>
        <div
          className="ac-sweep absolute inset-y-0 left-0 w-[26%] blur-[2px]"
          style={{
            background: `linear-gradient(90deg, transparent, ${mix(22)}, transparent)`,
          }}
        />
      </div>
      <div
        className="ac-edge absolute inset-y-0 left-0 w-[3px]"
        style={{ background: AC }}
        aria-hidden
      />

      <div className="relative flex items-center justify-between gap-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <ShieldMark />
          <div className="min-w-0">
            <div
              className="text-[12.5px] font-bold uppercase tracking-[0.09em]"
              style={{ color: AC, textShadow: `0 0 14px ${mix(45)}` }}
            >
              {scoped ? t("notice.clear") : t("notice.clearTitle")}
              {notices.length > 1 && <span className="ml-1 font-mono">×{notices.length}</span>}
            </div>
            <div className="mt-px truncate text-[10.5px] text-slate-400">
              {scoped ? t(`target.${head.target_type}`) : t(`region.${head.region}`, head.region)}
            </div>
          </div>
        </div>
        <div className="flex flex-none items-center gap-1.5">
          <DevId>N{head.id}</DevId>
          <EventTime iso={head.event_time} />
        </div>
      </div>

      <ClampText text={body} className="relative mt-2 break-words leading-snug text-slate-300" />

      {closed && (
        <div className="relative mt-2.5 flex items-center justify-between gap-2">
          <span
            className="flex items-center gap-1.5 rounded-md px-1.5 py-0.5 font-mono text-[10px]"
            style={{ background: mix(12), color: AC }}
          >
            <Clock size={10} className="flex-none" />
            {t("notice.clearLasted")} {durationLabel(t, closed.started_at, closed.ended_at!)}
          </span>
          {sources.length > 0 && (
            <span className="flex min-w-0 items-center gap-1.5 rounded-md bg-white/[0.05] px-1.5 py-0.5 text-[10px] text-slate-400">
              <RadioTower size={10} className="flex-none opacity-70" />
              <span className="truncate">{sources.join(" · ")}</span>
            </span>
          )}
        </div>
      )}

      {/* Without a matched alert there is no chip row, so the source falls back
          to the feed's normal (preference-gated) line. */}
      {!closed && <SourceName name={sources.join(" · ") || null} />}
    </li>
  );
}

/** The shield with the checkmark that draws itself in, inside two halo rings
 * that keep expanding out of it. Split out because it is eight nested absolute
 * layers and it was burying the card's actual content. */
function ShieldMark() {
  return (
    <div className="relative grid h-[26px] w-[26px] flex-none place-items-center" aria-hidden>
      <div className="ac-halo absolute inset-0 rounded-full border" style={{ borderColor: AC }} />
      <div
        className="ac-halo absolute inset-0 rounded-full border"
        style={{ borderColor: AC, animationDelay: "1.1s" }}
      />
      <div
        className="absolute inset-0 rounded-full border"
        style={{ background: mix(14), borderColor: mix(45) }}
      />
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke={AC}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="relative"
      >
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path className="ac-draw" d="M9 12l2 2 4-4" strokeDasharray="12" strokeDashoffset="12" />
      </svg>
    </div>
  );
}
