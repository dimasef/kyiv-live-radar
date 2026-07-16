import L from 'leaflet'
import type { CSSProperties } from 'react'
import { memo, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Circle,
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet'

import { useRadar } from '../../store'
import { CorroborationLine, CountBadge, threatState, typeLabel } from '../../threatDisplay'
import { HOME_COLOR, threatColor } from '../../theme'
import { DOT_UNTIL_MOVING, threatDivIcon } from '../../threatIcons'
import type { Threat } from '../../types'
import AxisEdgeIndicators from './AxisEdgeIndicators'
import CitywidePulse from './CitywidePulse'
import IncidentHighlight from './IncidentHighlight'
import MapLegend from './MapLegend'
import { hasMovement, headingOf, trackPoints } from './track'

const KYIV_CENTER: [number, number] = [50.4501, 30.5234]

/** Keeps Leaflet's cached container size in sync with the real DOM box.
 *
 * On mobile the map often mounts before its container has settled to full
 * height (dynamic viewport bar, bottom-sheet layout, PWA safe-area insets), so
 * Leaflet captures a too-short size and tiles render in a thin strip until the
 * user navigates away and back (which remounts at the correct size). A
 * ResizeObserver on the actual container calls invalidateSize() whenever the
 * box changes — first paint, orientation change, sheet reflow — so it always
 * self-corrects. */
function ResizeHandler() {
  const map = useMap()

  useEffect(() => {
    const container = map.getContainer()
    // Fire once after mount in case the container was already resized before the
    // observer attached (ResizeObserver only reports changes after subscribing,
    // but implementations deliver an initial callback — belt-and-suspenders).
    const kick = () => map.invalidateSize({ animate: false })
    const raf = requestAnimationFrame(kick)

    const ro = new ResizeObserver(kick)
    ro.observe(container)
    // Mobile Safari fires these without a corresponding element resize.
    window.addEventListener('orientationchange', kick)
    window.addEventListener('pageshow', kick)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('orientationchange', kick)
      window.removeEventListener('pageshow', kick)
    }
  }, [map])

  return null
}

/** Two expanding rings pulsing in the threat color — the live head of a track. */
function pulseIcon(color: string): L.DivIcon {
  return L.divIcon({
    className: 'pulse-wrap',
    html:
      `<span class="pulse-ring" style="--c:${color}"></span>` +
      `<span class="pulse-ring pulse-ring--slow" style="--c:${color}"></span>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  })
}

const homeIcon = L.divIcon({
  className: 'home-marker',
  html: `<svg width="22" height="22" viewBox="0 0 24 24" style="filter:drop-shadow(0 0 6px rgba(56,189,248,.6))">
    <path d="M12 3 L21 11 L18 11 L18 20 L14 20 L14 14 L10 14 L10 20 L6 20 L6 11 L3 11 Z"
      fill="${HOME_COLOR}" stroke="#0b0f14" stroke-width="1"/></svg>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
})

/** Handles map clicks (set home) and auto-recenters when geolocation resolves. */
function HomeController() {
  const map = useMap()
  const home = useRadar((s) => s.home)
  const setHome = useRadar((s) => s.setHome)
  const flown = useRef(false)

  useMapEvents({
    click(e) {
      const state = useRadar.getState()
      // Only place home when the user explicitly armed placement — otherwise a
      // click is just a map interaction and must not move home.
      if (!state.placingHome) return
      setHome({
        lat: e.latlng.lat,
        lon: e.latlng.lng,
        radiusKm: state.home?.radiusKm ?? 3,
        origin: 'manual',
      })
      state.setPlacingHome(false)
    },
  })

  useEffect(() => {
    if (home?.origin === 'geo' && !flown.current) {
      map.flyTo([home.lat, home.lon], 12)
      flown.current = true
    }
  }, [home, map])

  return null
}

/** Flies the map to fit an inspected track the moment its points arrive —
 * once per selection, not on every subsequent event update. */
function InspectController() {
  const map = useMap()
  const inspected = useRadar((s) => s.inspectedThreat)
  const liveThreats = useRadar((s) => s.threats)
  const fittedId = useRef<number | null>(null)

  useEffect(() => {
    if (!inspected) return
    if (fittedId.current === inspected.id) return
    // Prefer the live copy so an already-open track's points (and thus the
    // fly-to) are available instantly, instead of waiting on our own fetch.
    const display = liveThreats[inspected.id] ?? inspected
    const pts = trackPoints(display)
    if (pts.length === 0) return
    fittedId.current = inspected.id
    if (pts.length === 1) {
      map.flyTo([pts[0].lat, pts[0].lon], 13)
    } else {
      map.flyToBounds(
        pts.map((p) => [p.lat, p.lon] as [number, number]),
        { padding: [56, 56], maxZoom: 14 },
      )
    }
  }, [inspected, liveThreats, map])

  return null
}

function ThreatPopup({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const color = threatColor(threat)
  const label = typeLabel(threat, t)
  // The messages that produced this track — one per distinct source message
  // (an event repeated per district shares a message_id), oldest first so the
  // popup reads as the target's story.
  const messages: typeof threat.events = []
  const seen = new Set<number | string>()
  for (const ev of threat.events) {
    const key = ev.source_message_id ?? ev.raw_text
    if (seen.has(key)) continue
    seen.add(key)
    messages.push(ev)
  }
  return (
    <Popup>
      <div style={{ minWidth: 170, fontSize: 12 } as CSSProperties}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 99,
              background: color,
              boxShadow: `0 0 8px ${color}`,
              flex: 'none',
            }}
          />
          {label && <b style={{ fontSize: 13 }}>{label}</b>}
          <CountBadge
            count={threat.target_count}
            as="b"
            style={{ color: '#fbbf24', fontFamily: 'IBM Plex Mono, monospace' }}
          />
          <span style={{ opacity: 0.6, fontFamily: 'IBM Plex Mono, monospace' }}>
            {t(`status.${threat.status}`, threat.status)}
          </span>
        </div>
        <CorroborationLine
          threat={threat}
          as="div"
          style={{
            marginTop: 4,
            opacity: 0.75,
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: 11,
          }}
        />
        {threat.has_conflict && (
          <div style={{ color: '#fb923c', fontWeight: 600, marginTop: 3 }}>
            ⚠ {t('log.conflict')}
          </div>
        )}
        {messages.length > 0 && (
          <div
            style={{
              marginTop: 6,
              paddingTop: 6,
              borderTop: '1px solid rgba(255,255,255,0.1)',
              maxHeight: 150,
              overflowY: 'auto',
            }}
          >
            {messages.map((ev) => (
              <div key={ev.id} style={{ marginBottom: 6 }}>
                <div
                  style={{
                    display: 'flex',
                    gap: 6,
                    fontSize: 10,
                    opacity: 0.55,
                    fontFamily: 'IBM Plex Mono, monospace',
                  }}
                >
                  <span>
                    {new Date(ev.event_time).toLocaleTimeString('uk-UA', {
                      timeZone: 'Europe/Kyiv',
                      hour: '2-digit',
                      minute: '2-digit',
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
              fontFamily: 'IBM Plex Mono, monospace',
            }}
          >
            T{threat.id}
          </div>
        )}
      </div>
    </Popup>
  )
}

// Memoized so a new event on ONE track doesn't re-render every OTHER track's
// layer too — react-leaflet calls marker.setIcon() whenever the `icon` prop
// object changes identity, which makes Leaflet tear down and recreate the
// marker's DOM (the pulse-ring spans, the arrow svg), restarting their CSS
// keyframe animations from 0%. Unrelated markers would visibly "pop" back in
// on every unrelated update. Icons are additionally useMemo'd so even a
// re-render of THIS track's own layer reuses the same icon object when color
// and heading haven't actually changed.
const ThreatLayer = memo(function ThreatLayer({
  threat,
  highlighted = false,
}: {
  threat: Threat
  highlighted?: boolean
}) {
  const pts = trackPoints(threat)
  const color = threatColor(threat)
  // Only a track that actually moved over time gets a heading/vector — a single
  // multi-district message is an enumeration, not a trajectory (see hasMovement).
  // An impact is a POINT strike, never a trajectory: it must NEVER draw a
  // connecting vector even when re-reports give it several timestamps (a
  // ballistic can't "move" between districts) — so kind='impact' is excluded.
  const moved = threat.kind !== 'impact' && hasMovement(threat)
  const heading = moved ? headingOf(threat) : null
  const type = threat.target_type

  // Head-marker state: influences SHAPE. A hit bursts; a shot-down/lost track is
  // struck through; a moving track points along its heading. A cruise missile
  // with no heading yet is an honest dot (DOT_UNTIL_MOVING); drones and
  // ballistic/unknown show their glyph from the first sighting (a drone points
  // up until it gains a course, then rotates along the vector).
  const state = threatState(threat, { heading, directional: DOT_UNTIL_MOVING[type] })

  const pulse = useMemo(() => pulseIcon(color), [color])
  const headIcon = useMemo(
    () =>
      threatDivIcon(type, {
        state,
        bearingDeg: heading ?? 0,
        color,
        size: highlighted ? 30 : 26,
      }),
    [type, state, heading, color, highlighted],
  )

  if (pts.length === 0) return null
  // City-wide threats have no real location (their event sits on the city-centre
  // sentinel) — they're shown as a banner, not a map point. Skip rendering here.
  if (threat.scope === 'city') return null

  const latlngs = pts.map((p) => [p.lat, p.lon] as [number, number])
  const head = pts[pts.length - 1]
  const active = !threat.closed_at
  // Confidence is a VISUAL WEIGHT, not just popup text: a one-source guess reads
  // fainter than a multi-source confirmation. Floor at 0.5 so a low-confidence
  // marker is still legible. corroboration >= 2 adds a halo ring — real weight.
  const dim = 0.5 + 0.5 * Math.max(0, Math.min(1, threat.confidence))
  const corroborated = threat.corroboration_count >= 2

  return (
    <>
      {moved && latlngs.length > 1 && (
        <Polyline
          // className is applied at creation only — remount when activity flips.
          key={`${threat.id}-${active ? 'live' : 'closed'}-${highlighted ? 'insp' : ''}`}
          positions={latlngs}
          pathOptions={{
            color,
            weight: highlighted ? 5 : 3,
            opacity: (active ? 0.8 : highlighted ? 0.75 : 0.45) * dim,
            className: [active && 'track-flow', highlighted && 'track-inspect']
              .filter(Boolean)
              .join(' ') || undefined,
            dashArray: !active && threat.has_conflict ? '6 6' : undefined,
          }}
        />
      )}
      {pts.slice(0, -1).map((p, i) => (
        <CircleMarker
          key={i}
          center={[p.lat, p.lon]}
          radius={highlighted ? 4 : 3}
          pathOptions={{ color, fillColor: color, fillOpacity: 0.6 * dim, weight: highlighted ? 2 : 1 }}
        />
      ))}
      {/* Corroboration halo — a faint ring behind the head when >= 2 independent
          sources agree, so a well-attested target reads as heavier at a glance. */}
      {corroborated && (
        <CircleMarker
          center={[head.lat, head.lon]}
          radius={highlighted ? 16 : 13}
          interactive={false}
          pathOptions={{ color, weight: 1.5, opacity: 0.5 * dim, fillColor: color, fillOpacity: 0.06 }}
        />
      )}
      {/* Pulsing rings on the live head of an active track. */}
      {active && (
        <Marker
          position={[head.lat, head.lon]}
          icon={pulse}
          interactive={false}
          zIndexOffset={-100}
        />
      )}
      <Marker position={[head.lat, head.lon]} icon={headIcon} opacity={dim}>
        <ThreatPopup threat={threat} />
      </Marker>
    </>
  )
})

const DISTRICT_STYLE = {
  color: '#64748b',
  weight: 1,
  opacity: 0.45,
  fillColor: '#334155',
  fillOpacity: 0.1,
}

export default function MapView() {
  const { t } = useTranslation()
  const threats = useRadar((s) => s.threats)
  const boundaries = useRadar((s) => s.boundaries)
  const home = useRadar((s) => s.home)
  const placingHome = useRadar((s) => s.placingHome)
  const inspectedThreat = useRadar((s) => s.inspectedThreat)
  const initialCenter: [number, number] = home ? [home.lat, home.lon] : KYIV_CENTER

  // A track being inspected might already be live (in `threats`) — in that
  // case the live copy has fresher data, so just highlight it in place rather
  // than rendering a second, stale layer on top of it.
  const inspectedIsLive = inspectedThreat != null && inspectedThreat.id in threats

  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={initialCenter}
        zoom={home ? 12 : 11}
        className={placingHome ? 'placing-home' : undefined}
        style={{ height: '100%', width: '100%', background: '#05080d' }}
      >
        <TileLayer
          attribution='&copy; OpenStreetMap &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />

        {/* Real OSM raion boundaries — a non-interactive context layer: clicks
            pass through to the map (pan / home placement) and no focus outline. */}
        {boundaries.map((b) => (
          <GeoJSON key={b.id} data={b.geojson} style={DISTRICT_STYLE} interactive={false} />
        ))}
        {/* Attack heat (raions under an active incident) + city-wide pulse layer
            over the inert base boundaries. */}
        <IncidentHighlight />
        <CitywidePulse />

        <ResizeHandler />
        <HomeController />
        <InspectController />

        {home && (
          <>
            <Circle
              center={[home.lat, home.lon]}
              radius={home.radiusKm * 1000}
              pathOptions={{ color: HOME_COLOR, fillColor: HOME_COLOR, fillOpacity: 0.06, weight: 1 }}
            />
            <Marker position={[home.lat, home.lon]} icon={homeIcon}>
              <Tooltip direction="top" offset={[0, -18]}>
                {t('legend.home')} · {home.lat.toFixed(4)}, {home.lon.toFixed(4)}
              </Tooltip>
            </Marker>
          </>
        )}

        {Object.values(threats).map((th) => (
          <ThreatLayer
            key={th.id}
            threat={th}
            highlighted={inspectedThreat?.id === th.id}
          />
        ))}
        {/* The inspected track isn't currently live (closed/evicted) — render
            it from its independently-fetched event history. */}
        {inspectedThreat && !inspectedIsLive && (
          <ThreatLayer threat={inspectedThreat} highlighted />
        )}
      </MapContainer>
      <AxisEdgeIndicators />
      <MapLegend />
    </div>
  )
}
