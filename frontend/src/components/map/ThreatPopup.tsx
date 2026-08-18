import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { Popup } from "react-leaflet";

import HomeDistance from "@/components/common/HomeDistance";
import AnalyzeButton from "@/components/game/AnalyzeButton";
import { kyivClock } from "@/lib/kyivTime";
import { isQuiet, minutesSinceSeen } from "@/lib/threatFreshness";
import { useRadar } from "@/store";

import { CorroborationLine, CountBadge, typeLabel } from "../../threatDisplay";
import { threatChip } from "../../threatLabels";
import { threatColor } from "../../theme";
import type { Threat } from "../../types";

export default function ThreatPopup({ threat }: { threat: Threat }) {
  const { t } = useTranslation();
  const gamification = useRadar((s) => s.gamification);
  const now = useRadar((s) => s.nowMs + s.clockSkewMs);
  const color = threatColor(threat);
  // Same source as the feed's StatusChip — the two must never disagree.
  const chip = threatChip(threat);
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
        {/* wrap: type name + ×N + a long chip ("НЕ ПІДТВЕРДЖЕНО") together
            exceed the popup's min width, and wrapping beats overflowing. */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
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
          {/* Lifecycle chip — same idiom as the feed's StatusChip (uppercase
              micro-caps on a 10%-alpha wash of its own colour), so one state
              looks the same wherever it appears. */}
          <span
            style={{
              padding: "1px 4px",
              borderRadius: 4,
              fontSize: 12,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              whiteSpace: "nowrap",
              color: chip.color,
              background: `${chip.color}1a`,
            }}
          >
            {t(chip.labelKey)}
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
        {/* Names the reason a target looks faded — "seen 14 min ago" is the
            fade in words, and the number is what an operator actually acts on. */}
        {isQuiet(threat, now) && (
          <div
            style={{
              marginTop: 4,
              fontSize: 11,
              opacity: 0.7,
              fontFamily: "IBM Plex Mono, monospace",
            }}
          >
            {t("threat.lastSeen", { n: minutesSinceSeen(threat, now) })}
          </div>
        )}
        <HomeDistance threat={threat} className="mt-1" />
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
                  <span>{kyivClock(ev.event_time)}</span>
                  {ev.source_name && <span>{ev.source_name}</span>}
                </div>
                <div style={{ fontSize: 11, lineHeight: 1.35, opacity: 0.9 }}>{ev.raw_text}</div>
              </div>
            ))}
          </div>
        )}
        {gamification && (
          <div
            style={{
              marginTop: 8,
              paddingTop: 8,
              borderTop: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            <AnalyzeButton threat={threat} />
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
