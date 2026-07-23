import { ChevronUp } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { OnlineBadge, ThreatLog } from "@/components/feed";
import { useRadar } from "@/store";
import type { SheetHeight } from "@/store/prefsSlice";

// Open height per user preference. Literal classes so Tailwind's JIT keeps them.
const HEIGHT_CLASS: Record<SheetHeight, string> = {
  low: "h-[32dvh]",
  mid: "h-[62dvh]",
  high: "h-[80dvh]",
};

/** Mobile bottom sheet for the event feed. Reads placingHome/inspectedThreat
 * straight from the store to auto-collapse (both need the map visible). Settings
 * moved to the shell drawer, so this is feed-only now. */
export default function MobileSheet() {
  const { t } = useTranslation();
  const placingHome = useRadar((s) => s.placingHome);
  const inspectedThreatId = useRadar((s) => s.inspectedThreat?.id);
  const sheetHeight = useRadar((s) => s.sheetHeight);
  const [sheetOpen, setSheetOpen] = useState(false);

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
        className="flex-none flex items-center justify-between gap-3 px-6 h-[3.4rem] w-full text-left"
      >
        <span className="flex items-center gap-2.5 min-w-0">
          <span className="w-8 h-1 rounded-full bg-white/15" aria-hidden />
          {/* Collapsed: draw the eye to the feed with the phosphor accent. */}
          <span className={`panel-title ${sheetOpen ? "" : "text-phosphor-soft"}`}>
            {t("log.title")}
          </span>
        </span>
        <span className="flex items-center gap-3">
          <OnlineBadge />
          <ChevronUp
            size={24}
            className={`text-slate-400 transition-transform duration-300 ${
              sheetOpen ? "rotate-180" : ""
            }`}
            aria-hidden
          />
        </span>
      </button>

      <div className="flex-1 min-h-0 overflow-y-auto scroll-slim px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <ThreatLog />
      </div>
    </section>
  );
}
