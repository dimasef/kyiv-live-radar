import { Analytics } from "@vercel/analytics/react";
import { useEffect, useState } from "react";

import { RegionLayerHint, StatusBanner, ZoneLayerNotice } from "@/components/banners";
import {
  AppStatus,
  DisclaimerModal,
  FeedToggle,
  MobileSheet,
  RegionPickerModal,
} from "@/components/chrome";
import { ThreatLog } from "@/components/feed";
import { MapView } from "@/components/map";
import { riseDelay } from "@/lib/motion";
import { safeGet, STORAGE_KEYS } from "@/lib/storage";
import { useRadar } from "@/store";
import { bootstrapApp } from "@/store/bootstrap";

/** Ties the collapse handle to the rail it controls, for `aria-controls`. */
const FEED_RAIL_ID = "feed-rail";

/** The radar map view (default route). Renders inside the persistent AppShell,
 * so it owns only the map region: the map itself, its overlay stack (air-alert
 * banner + inspect badge), the desktop feed sidebar, and the mobile feed sheet.
 * Navigation, status, and settings live in the shell. */
export default function App() {
  const [showDisclaimer, setShowDisclaimer] = useState(
    () => safeGet(STORAGE_KEYS.disclaimerHide) !== "1",
  );
  const feedCollapsed = useRadar((s) => s.feedCollapsed);
  const chosenRegion = useRadar((s) => s.chosenRegion);
  const regions = useRadar((s) => s.regions);
  // Only once the catalogue has arrived — an empty picker would ask a question
  // with no answers on it. The disclaimer goes first: it is the safety notice,
  // and stacking two modals would bury it.
  const needsRegion = !showDisclaimer && chosenRegion == null && regions.length > 0;

  useEffect(() => {
    bootstrapApp();
  }, []);

  return (
    <div className="h-full lg:flex">
      {showDisclaimer && <DisclaimerModal onClose={() => setShowDisclaimer(false)} />}
      {needsRegion && <RegionPickerModal />}

      {/* Map fills the shell slot; on mobile the sheet floats above it. */}
      <div className="absolute inset-0 lg:relative lg:flex-1 lg:min-w-0">
        <MapView />
        {/* Map overlays — pinned to the top of the map, not the navbar. */}
        {/* A column, so a second pill stacks under the banner rather than
            competing for its line — see banners/ZoneLayerNotice. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-[1000] flex flex-col items-center gap-2 px-3 pt-3">
          <StatusBanner />
          <ZoneLayerNotice />
          <RegionLayerHint />
        </div>
        {/* Connection status — top-right corner of the map. */}
        <div className="absolute right-3 top-3 z-[1000]">
          <AppStatus />
        </div>
        {/* Lives on the MAP, not in the rail: the rail unmounts when collapsed,
            so a handle inside it could never bring it back. */}
        <FeedToggle id={FEED_RAIL_ID} />
      </div>

      {/* Desktop feed sidebar (settings moved to the shell drawer). Unmounted
          rather than hidden when collapsed — the feed's data lives in the store,
          so nothing is lost and reopening shows everything that arrived
          meanwhile. Collapsing changes the map container's width, which
          ResizeHandler's observer turns into an invalidateSize(). */}
      {!feedCollapsed && (
        <aside
          id={FEED_RAIL_ID}
          className="hidden lg:flex w-[344px] shrink-0 flex-col gap-3 p-3 min-h-0 border-l border-white/5 bg-ink-900/55 backdrop-blur-xl"
        >
          <div className="rise flex-1 min-h-0 flex flex-col" style={riseDelay(1)}>
            <ThreatLog />
          </div>
        </aside>
      )}

      <MobileSheet />
      <Analytics />
    </div>
  );
}
