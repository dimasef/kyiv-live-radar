import type L from "leaflet";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { centerPinMode } from "../../lib/device";
import { useRadar } from "../../store";
import { HOME_COLOR } from "../../theme";

// The same house silhouette as MapView's placed home marker, so the placement
// preview matches exactly what lands on the map.
const houseSvg = (size: number) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="filter:drop-shadow(0 0 6px ${HOME_COLOR})">
    <path d="M12 3 L21 11 L18 11 L18 20 L14 20 L14 14 L10 14 L10 20 L6 20 L6 11 L3 11 Z"
      fill="${HOME_COLOR}" stroke="#0b0f14" stroke-width="1"/></svg>`;

export default function HomePlacement({ map }: { map: L.Map | null }) {
  const { t } = useTranslation();
  const placingHome = useRadar((s) => s.placingHome);
  const setHome = useRadar((s) => s.setHome);
  const setPlacingHome = useRadar((s) => s.setPlacingHome);
  const ghostRef = useRef<HTMLDivElement>(null);
  const centerMode = centerPinMode();

  useEffect(() => {
    if (!placingHome || !centerMode || !map) return;
    const home = useRadar.getState().home;
    if (home) map.setView([home.lat, home.lon]);
  }, [placingHome, centerMode, map]);

  useEffect(() => {
    if (!placingHome || centerMode || !map) return;
    const container = map.getContainer();
    const ghost = ghostRef.current;
    if (!ghost) return;
    const move = (e: MouseEvent) => {
      ghost.style.opacity = "1";
      ghost.style.transform = `translate(${e.clientX}px, ${e.clientY}px) translate(0px, -90%)`;
    };
    const hide = () => {
      ghost.style.opacity = "0";
    };
    container.addEventListener("mousemove", move);
    container.addEventListener("mouseleave", hide);
    return () => {
      container.removeEventListener("mousemove", move);
      container.removeEventListener("mouseleave", hide);
    };
  }, [placingHome, centerMode, map]);

  if (!placingHome) return null;

  if (centerMode) {
    const confirm = () => {
      if (!map) return;
      const c = map.getCenter();
      const cur = useRadar.getState().home;
      setHome({ lat: c.lat, lon: c.lng, radiusKm: cur?.radiusKm ?? 3, origin: "manual" });
      setPlacingHome(false);
    };
    return (
      <div className="pointer-events-none absolute inset-0 z-[1200] flex flex-col items-center justify-center">
        <span aria-hidden dangerouslySetInnerHTML={{ __html: houseSvg(30) }} />
        <div className="pointer-events-auto mt-4 flex items-center gap-2">
          <button onClick={confirm} className="btn btn--accent px-4 py-2 shadow-lg">
            {t("home.confirmPlace")}
          </button>
          <button onClick={() => setPlacingHome(false)} className="btn px-3 py-2 shadow-lg">
            {t("home.cancel")}
          </button>
        </div>
      </div>
    );
  }

  // Desktop cursor-follow ghost (viewport-fixed, positioned from clientX/Y).
  return (
    <div
      ref={ghostRef}
      aria-hidden
      className="pointer-events-none fixed left-0 top-0 z-[1200] opacity-0"
      style={{ willChange: "transform" }}
      dangerouslySetInnerHTML={{ __html: houseSvg(26) }}
    />
  );
}
