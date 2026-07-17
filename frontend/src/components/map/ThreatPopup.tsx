import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Popup } from "react-leaflet";

import { CorroborationLine, CountBadge, typeLabel } from "../../threatDisplay";
import { threatColor } from "../../theme";
import type { Threat } from "../../types";

export default function ThreatPopup({ threat }: { threat: Threat }) {
  const { t } = useTranslation();
  const color = threatColor(threat);
  const label = typeLabel(threat, t);
  // The messages that produced this track — one per distinct source message
  // (an event repeated per district shares a message_id), oldest first so the
  // popup reads as the target's story.
  const messages: typeof threat.events = [];
  const seen = new Set<number | string>();
  for (const ev of threat.events) {
    const key = ev.source_message_id ?? ev.raw_text;
    if (seen.has(key)) continue;
    seen.add(key);
    messages.push(ev);
  }
  return (
    <Popup>
      <div style={{ minWidth: 170, fontSize: 12 } as CSSProperties}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 99,
              background: color,
              boxShadow: `0 0 8px ${color}`,
              flex: "none",
            }}
          />
          {label && <b style={{ fontSize: 13 }}>{label}</b>}
          <CountBadge
            count={threat.target_count}
            as="b"
            style={{ color: "#fbbf24", fontFamily: "IBM Plex Mono, monospace" }}
          />
          <span style={{ opacity: 0.6, fontFamily: "IBM Plex Mono, monospace" }}>
            {t(`status.${threat.status}`, threat.status)}
          </span>
        </div>
        <CorroborationLine
          threat={threat}
          as="div"
          style={{
            marginTop: 4,
            opacity: 0.75,
            fontFamily: "IBM Plex Mono, monospace",
            fontSize: 11,
          }}
        />
        {threat.has_conflict && (
          <div style={{ color: "#fb923c", fontWeight: 600, marginTop: 3 }}>
            ⚠ {t("log.conflict")}
          </div>
        )}
        {messages.length > 0 && (
          <div
            style={{
              marginTop: 6,
              paddingTop: 6,
              borderTop: "1px solid rgba(255,255,255,0.1)",
              maxHeight: 150,
              overflowY: "auto",
            }}
          >
            {messages.map((ev) => (
              <div key={ev.id} style={{ marginBottom: 6 }}>
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    fontSize: 10,
                    opacity: 0.55,
                    fontFamily: "IBM Plex Mono, monospace",
                  }}
                >
                  <span>
                    {new Date(ev.event_time).toLocaleTimeString("uk-UA", {
                      timeZone: "Europe/Kyiv",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  {ev.source_name && <span>{ev.source_name}</span>}
                </div>
                <div style={{ fontSize: 11, lineHeight: 1.35, opacity: 0.9 }}>{ev.raw_text}</div>
              </div>
            ))}
          </div>
        )}
        {import.meta.env.DEV && (
          <div
            style={{
              marginTop: 4,
              fontSize: 10,
              opacity: 0.45,
              fontFamily: "IBM Plex Mono, monospace",
            }}
          >
            T{threat.id}
          </div>
        )}
      </div>
    </Popup>
  );
}
