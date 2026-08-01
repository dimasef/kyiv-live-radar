import { Check, Clock, Loader2, Microscope } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { analysisKindFor, isAnalysableTarget, isStale } from "@/lib/cards";

import { analyzeButtonState } from "./analyzeButtonState";
import { useRadar } from "@/store";
import type { Threat } from "@/types";

export default function AnalyzeButton({ threat }: { threat: Threat }) {
  const { t } = useTranslation();
  const authed = useRadar((s) => s.authStatus === "authed");
  const state = useRadar((s) => s.threatStates[threat.id]);
  const failed = useRadar((s) => !!s.threatStateFailed[threat.id]);
  const analyzing = useRadar((s) => s.analyzing);
  const ensureThreatState = useRadar((s) => s.ensureThreatState);
  const analyze = useRadar((s) => s.analyze);

  const kind = analysisKindFor(threat);

  useEffect(() => {
    if (authed && kind) void ensureThreatState(threat.id).catch(() => {});
  }, [authed, kind, threat.id, ensureThreatState]);

  if (!authed) return null;

  if (!kind) {
    if (isAnalysableTarget(threat) && isStale(threat)) {
      return (
        <span className="flex items-center gap-1 rounded-full bg-white/[0.04] px-2 py-1 text-[11px] text-slate-500">
          <Clock size={12} /> {t("game.stale")}
        </span>
      );
    }
    return null;
  }

  const busy = analyzing?.threatId === threat.id;

  switch (analyzeButtonState({ kind, state, failed, busy })) {
    case "checking":
      return (
        <span className="flex items-center gap-1 rounded-full bg-white/[0.04] px-2.5 py-1 text-[11px] text-slate-600">
          <Loader2 size={12} className="animate-spin" />
          {t("game.checking")}
        </span>
      );
    case "collected":
      return (
        <span className="flex items-center gap-1 rounded-full bg-white/[0.04] px-2 py-1 text-[11px] font-medium text-slate-500">
          <Check size={12} /> {t("game.collected")}
        </span>
      );
    case "taken":
      return (
        <span className="rounded-full bg-white/[0.04] px-2 py-1 text-[11px] text-slate-500">
          {t("game.taken")}
        </span>
      );
    case "busy":
    case "available":
      return (
        <button
          onClick={() => void analyze(threat.id, kind)}
          disabled={!!analyzing}
          className="flex items-center gap-1 rounded-full border border-phosphor/30 bg-phosphor/10 px-2.5 py-1 text-[11px] font-medium text-phosphor-soft transition-colors duration-200 hover:bg-phosphor/20 disabled:opacity-50"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Microscope size={12} />}
          {busy ? t("game.analyzing") : kind === "remains" ? t("game.analyzeRemains") : t("game.analyze")}
        </button>
      );
  }
}
