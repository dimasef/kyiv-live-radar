import { Analytics } from "@vercel/analytics/react";
import { useEffect, useState } from "react";

import { StatusBanner } from "@/components/banners";
import { AppStatus, DisclaimerModal, MobileSheet, SplashScreen } from "@/components/chrome";
import { ThreatLog } from "@/components/feed";
import { InspectBadge, MapView } from "@/components/map";
import { riseDelay } from "@/lib/motion";
import { safeGet, STORAGE_KEYS } from "@/lib/storage";
import { bootstrapApp } from "@/store/bootstrap";

/** The radar map view (default route). Renders inside the persistent AppShell,
 * so it owns only the map region: the map itself, its overlay stack (air-alert
 * banner + inspect badge), the desktop feed sidebar, and the mobile feed sheet.
 * Navigation, status, and settings live in the shell. */
export default function App() {
  const [showDisclaimer, setShowDisclaimer] = useState(
    () => safeGet(STORAGE_KEYS.disclaimerHide) !== "1",
  );

  useEffect(() => {
    bootstrapApp();
  }, []);

  return (
    <div className="h-full lg:flex">
      <SplashScreen />
      {showDisclaimer && <DisclaimerModal onClose={() => setShowDisclaimer(false)} />}

      {/* Map fills the shell slot; on mobile the sheet floats above it. */}
      <div className="absolute inset-0 lg:relative lg:flex-1 lg:min-w-0">
        <MapView />
        {/* Map overlays — pinned to the top of the map, not the navbar. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-[1000] flex flex-col items-center gap-2 px-3 pt-3">
          <StatusBanner />
          <InspectBadge />
        </div>
        {/* Connection status — top-right corner of the map. */}
        <div className="absolute right-3 top-3 z-[1000]">
          <AppStatus />
        </div>
      </div>

      {/* Desktop feed sidebar (settings moved to the shell drawer). */}
      <aside className="hidden lg:flex w-[344px] shrink-0 flex-col gap-3 p-3 min-h-0 border-l border-white/5 bg-ink-900/55 backdrop-blur-xl">
        <div className="rise flex-1 min-h-0 flex flex-col" style={riseDelay(1)}>
          <ThreatLog />
        </div>
      </aside>

      <MobileSheet />
      <Analytics />
    </div>
  );
}
