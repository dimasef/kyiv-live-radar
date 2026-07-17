import { Loader2, WifiOff } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useRadar } from "@/store";

export default function ConnectionToast() {
  const { t } = useTranslation();
  const connected = useRadar((s) => s.connected);
  const resyncing = useRadar((s) => s.resyncing);

  if (connected && !resyncing) return null;

  if (connected && resyncing) {
    return (
      <div
        role="status"
        aria-label={t("conn.resyncing")}
        title={t("conn.resyncing")}
        className="banner-enter panel flex h-8 w-8 items-center justify-center rounded-full shadow-xl"
        style={{ borderColor: "#67e8f966", color: "var(--phosphor-soft)" }}
      >
        <Loader2 size={15} className="animate-spin [animation-duration:1.4s]" />
      </div>
    );
  }

  const accent = "#f87171";
  return (
    <div
      role="status"
      className="banner-enter panel flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-3.5 shadow-xl"
      style={{ borderColor: `${accent}40` }}
    >
      <span
        className="flex h-7 w-7 flex-none items-center justify-center rounded-full"
        style={{ background: `${accent}1f`, color: accent }}
      >
        <WifiOff size={14} className="animate-pulse" />
      </span>
      <span className="flex flex-col leading-tight">
        <span className="whitespace-nowrap text-xs font-semibold text-slate-100">
          {t("conn.lost")}
        </span>
        <span className="whitespace-nowrap text-[10px] text-slate-400">{t("conn.lostHint")}</span>
      </span>
    </div>
  );
}
