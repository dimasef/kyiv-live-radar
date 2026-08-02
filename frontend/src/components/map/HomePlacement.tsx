import type L from "leaflet";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { contactMarkerSvg, homeStyleOf } from "../../lib/contactMarker";
import { centerPinMode } from "../../lib/device";
import { useRadar } from "../../store";

export default function HomePlacement({ map }: { map: L.Map | null }) {
  const { t } = useTranslation();
  const placingHome = useRadar((s) => s.placingHome);
  // The marker the user actually picked, so the placement ghost is exactly what
  // will land on the map.
  const style = homeStyleOf(useRadar((s) => s.homeStyle));
  const houseSvg = (size: number) =>
    contactMarkerSvg(style.icon, style.color, size, style.glow);
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
