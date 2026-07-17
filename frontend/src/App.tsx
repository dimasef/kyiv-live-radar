import { Analytics } from "@vercel/analytics/react";
import { useEffect, useState } from "react";

import { StatusBanner } from "@/components/banners";
import {
  ConnectionToast,
  DisclaimerModal,
  Header,
  MobileSheet,
  SettingsPanel,
  SplashScreen,
  UpdateToast,
} from "@/components/chrome";
import { ThreatLog } from "@/components/feed";
import { InspectBadge, MapView } from "@/components/map";
import { riseDelay } from "@/lib/motion";
import { safeGet, STORAGE_KEYS } from "@/lib/storage";
import { bootstrapApp } from "@/store/bootstrap";

export default function App() {
  const [showDisclaimer, setShowDisclaimer] = useState(
    () => safeGet(STORAGE_KEYS.disclaimerHide) !== "1",
  );

  useEffect(() => {
    bootstrapApp();
  }, []);

  return (
    <div className="h-full flex flex-col">
      <SplashScreen />
      <Header />

      <DisclaimerModal open={showDisclaimer} onClose={() => setShowDisclaimer(false)} />
      <UpdateToast />
      <ConnectionToast />

      <main className="relative flex-1 min-h-0 lg:flex">
        {/* Map fills everything; on mobile the sheet floats above it. */}
        <div className="absolute inset-0 lg:relative lg:flex-1 lg:min-w-0">
          <MapView />
          <div className="pointer-events-none absolute inset-x-0 top-0 z-[1000] flex flex-col items-center gap-2 px-3 pt-3">
            <StatusBanner />
            <InspectBadge />
          </div>
        </div>

        {/* Desktop sidebar */}
        <aside className="hidden lg:flex w-[344px] shrink-0 flex-col gap-3 p-3 min-h-0 border-l border-white/5 bg-ink-900/55 backdrop-blur-xl">
          <div className="rise" style={riseDelay(1)}>
            <SettingsPanel />
          </div>
          <div className="rise flex-1 min-h-0 flex flex-col" style={riseDelay(2)}>
            <ThreatLog />
          </div>
        </aside>

        <MobileSheet />
      </main>
      <Analytics />
    </div>
  );
}
