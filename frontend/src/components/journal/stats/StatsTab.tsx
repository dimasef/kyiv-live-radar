import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchJournalStats } from "@/api";
import { riseDelay } from "@/lib/motion";
import type { AnalyticsPeriod, JournalStats } from "@/types";

import { useDistrictNames } from "../useDistrictNames";
import DistrictBars from "./DistrictBars";
import HeaviestDays from "./HeaviestDays";
import HourOfDay from "./HourOfDay";
import PeriodSwitch from "./PeriodSwitch";
import StatsOverview from "./StatsOverview";
import TypeTable from "./TypeTable";
import TypeTrend from "./TypeTrend";

function Section({
  delay,
  children,
}: {
  delay: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rise panel mt-4 p-4 sm:p-5" style={riseDelay(delay)}>
      {children}
    </div>
  );
}

/** The journal's statistics tab: one period switch, then every chart against
 * that same slice. */
export default function StatsTab({
  onOpenDay,
}: {
  onOpenDay: (date: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language?.startsWith("en") ? "en-GB" : "uk-UA";
  const [period, setPeriod] = useState<AnalyticsPeriod>("30d");
  const [stats, setStats] = useState<JournalStats | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const districtName = useDistrictNames();

  useEffect(() => {
    let cancelled = false;
    setPhase("loading");
    fetchJournalStats(period)
      .then((s) => {
        if (cancelled) return;
        setStats(s);
        setPhase("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, [period]);


  if (phase === "error") {
    return (
      <Section delay={2}>
        <div className="py-8 text-center text-xs text-slate-500">
          {t("journal.loadError")}
        </div>
      </Section>
    );
  }
  if (!stats) {
    return (
      <Section delay={2}>
        <div className="h-40 animate-pulse rounded-lg bg-white/[0.03]" />
      </Section>
    );
  }

  const hasTargets = stats.totals.targets + stats.totals.impacts > 0;

  return (
    // While a new period loads, the previous render stays put at reduced opacity
    // — no skeleton flash, no layout jump.
    <div
      className={
        phase === "loading"
          ? "opacity-50 transition-opacity"
          : "transition-opacity"
      }
    >
      <Section delay={2}>
        {/* Stacks on a phone: the switch takes the full row and the date range
            drops under it, instead of the two fighting over one line. */}
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
          <PeriodSwitch
            value={period}
            onChange={setPeriod}
            disabled={phase === "loading"}
          />
          <span className="whitespace-nowrap font-mono text-[11px] tabular-nums text-slate-600">
            {stats.from_date} → {stats.to_date}
          </span>
        </div>
        <StatsOverview stats={stats} />
      </Section>

      {!hasTargets ? (
        <Section delay={3}>
          <div className="py-6 text-center text-xs text-slate-500">
            {t("journal.stats.noData")}
          </div>
        </Section>
      ) : (
        <>
          <Section delay={3}>
            <HourOfDay
              hours={stats.hours}
              alertDaysObserved={stats.alert_days_observed}
            />
            {stats.alert_from_date &&
              stats.alert_from_date > stats.from_date && (
                <p className="mt-3 border-t border-white/[0.06] pt-3 text-xs leading-relaxed text-slate-500">
                  {t("journal.stats.alertWindowNote", {
                    from: stats.alert_from_date,
                  })}
                </p>
              )}
          </Section>

          <Section delay={4}>
            <TypeTrend days={stats.days} locale={locale} />
            <div className="mt-5 border-t border-white/[0.06] pt-4">
              <TypeTable
                typeTotals={stats.type_totals}
                typeDays={stats.type_days}
              />
            </div>
          </Section>

          <Section delay={5}>
            <DistrictBars
              districts={stats.districts}
              districtName={districtName}
            />
          </Section>

          <Section delay={6}>
            <HeaviestDays
              days={stats.days}
              locale={locale}
              onOpenDay={onOpenDay}
            />
          </Section>
        </>
      )}
    </div>
  );
}
