import { Check, Clock, Loader2, Microscope, User } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { analysisKindFor } from "@/lib/cards";

import { analyzeButtonState, showsAnalyzeAffordance, takenBy } from "./analyzeButtonState";
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

  if (!showsAnalyzeAffordance(threat, authed)) return null;

  // The only way past the guard above without a kind: analysable, but its
  // debris went cold.
  if (!kind) {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-white/[0.04] px-3 py-1.5 text-xs text-slate-500">
        <Clock size={14} /> {t("game.stale")}
      </span>
    );
  }

  const busy = analyzing?.threatId === threat.id;

  switch (analyzeButtonState({ kind, state, failed, busy })) {
    case "checking":
      return (
        <span className="flex items-center gap-1.5 rounded-full bg-white/[0.04] px-3 py-1.5 text-xs text-slate-600">
          <Loader2 size={14} className="animate-spin" />
          {t("game.checking")}
        </span>
      );
    case "collected":
      return (
        <span className="flex items-center gap-1.5 rounded-full bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-slate-500">
          <Check size={14} /> {t("game.collected")}
        </span>
      );
    case "taken": {
      // Naming whoever got here first, when they have a name to be named by.
      // `max-w` + `truncate` rather than slicing the string: the popup is a
      // fixed 270px and a display name can be anything, so the cut belongs to
      // the font's real metrics, not to a character count.
      const by = takenBy(kind, state);
      return (
        <span
          className="flex items-center gap-1.5 rounded-full bg-white/[0.04] px-3 py-1.5 text-xs text-slate-500"
          title={by ? t("game.takenBy", { name: by }) : t("game.taken")}
        >
          {by ? (
            <>
              <User size={14} className="flex-none" />
              <span className="max-w-[130px] truncate">{by}</span>
            </>
          ) : (
            t("game.taken")
          )}
        </span>
      );
    }
    case "busy":
    case "available":
      return (
        <button
          onClick={() => void analyze(threat.id, kind)}
          disabled={!!analyzing}
          className="flex items-center gap-1.5 rounded-full border border-phosphor/30 bg-phosphor/10 px-3 py-1.5 text-xs font-medium text-phosphor-soft transition-colors duration-200 hover:bg-phosphor/20 disabled:opacity-50"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Microscope size={14} />}
          {busy ? t("game.analyzing") : kind === "remains" ? t("game.analyzeRemains") : t("game.analyze")}
        </button>
      );
  }
}
