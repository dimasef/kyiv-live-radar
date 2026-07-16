import { ChevronUp } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ThreatLog } from "@/components/feed";
import { useRadar } from "@/store";
import type { SheetHeight } from "@/store/prefsSlice";

import SettingsPanel from "./SettingsPanel";

const TABS = ["feed", "settings"] as const;

// Open height per user preference. Literal classes so Tailwind's JIT keeps them.
const HEIGHT_CLASS: Record<SheetHeight, string> = {
  low: "h-[32dvh]",
  mid: "h-[62dvh]",
  high: "h-[80dvh]",
};

/** Mobile bottom sheet — expanded state + which tab is shown. Reads
 * placingHome/inspectedThreat straight from the store to auto-collapse
 * (both need the map visible), instead of App lifting that state down. */
export default function MobileSheet() {
  const { t } = useTranslation();
  const placingHome = useRadar((s) => s.placingHome);
  const inspectedThreatId = useRadar((s) => s.inspectedThreat?.id);
  const sheetHeight = useRadar((s) => s.sheetHeight);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [tab, setTab] = useState<(typeof TABS)[number]>("feed");

  useEffect(() => {
    if (placingHome) setSheetOpen(false);
  }, [placingHome]);
  useEffect(() => {
    if (inspectedThreatId != null) setSheetOpen(false);
  }, [inspectedThreatId]);

  return (
    <section
      className={`sheet lg:hidden absolute inset-x-0 bottom-0 z-[1100] ${HEIGHT_CLASS[sheetHeight]} flex flex-col rounded-t-2xl border-t border-x border-white/10 bg-ink-900/90 backdrop-blur-2xl shadow-[0_-18px_50px_-20px_rgba(0,0,0,0.8)] ${
        sheetOpen ? "translate-y-0" : "translate-y-[calc(100%-3.4rem)]"
      }`}
    >
      <button
        onClick={() => setSheetOpen(!sheetOpen)}
        aria-label={sheetOpen ? t("panel.close") : t("panel.open")}
        className="flex-none flex items-center justify-between gap-3 px-4 h-[3.4rem] w-full text-left"
      >
        <span className="flex items-center gap-2.5 min-w-0">
          <span className="w-8 h-1 rounded-full bg-white/15" aria-hidden />
          <span className="panel-title">{t("log.title")}</span>
        </span>
        <ChevronUp
          size={16}
          className={`text-slate-400 transition-transform duration-300 ${
            sheetOpen ? "rotate-180" : ""
          }`}
          aria-hidden
        />
      </button>

      <div className="flex-none flex gap-1 px-3 pb-2">
        {TABS.map((k) => (
          <button
            key={k}
            onClick={() => {
              setTab(k);
              setSheetOpen(true);
            }}
            className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-200 ${
              tab === k
                ? "bg-phosphor/15 text-phosphor-soft border border-phosphor/30"
                : "bg-white/[0.04] text-slate-400 border border-transparent"
            }`}
          >
            {t(`panel.${k}`)}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto scroll-slim px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {tab === "feed" ? <ThreatLog /> : <SettingsPanel defaultOpen />}
      </div>
    </section>
  );
}
