import L from 'leaflet'
import type { CSSProperties } from 'react'
import { useEffect, useRef } from 'react'
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

import { headingOf, trackPoints } from '../geo'
import { useRadar } from '../store'
import { threatColor } from '../theme'
import type { Threat } from '../types'
import MapLegend from './MapLegend'

const KYIV_CENTER: [number, number] = [50.4501, 30.5234]

function arrowIcon(color: string, deg: number): L.DivIcon {
  return L.divIcon({
    className: 'threat-arrow',
    html: `<svg width="26" height="26" viewBox="0 0 24 24" style="transform:rotate(${deg}deg);--glow:${color}66">
      <path d="M12 2 L18 20 L12 15 L6 20 Z" fill="${color}" stroke="#000" stroke-width="1"/>
    </svg>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
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
      fill="#38bdf8" stroke="#0b0f14" stroke-width="1"/></svg>`,
  iconSize: [22, 22],
  iconAnchor: [11, 20],
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

function ThreatPopup({ threat }: { threat: Threat }) {
  const { t } = useTranslation()
  const color = threatColor(threat)
  const sources = Array.from(
    new Set(threat.events.map((e) => e.source_name).filter(Boolean)),
  )
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
          <b style={{ fontSize: 13 }}>{t(`target.${threat.target_type}`)}</b>
          {threat.target_count > 1 && (
            <b style={{ color: '#fbbf24', fontFamily: 'IBM Plex Mono, monospace' }}>
              ×{threat.target_count}
            </b>
          )}
          <span style={{ opacity: 0.6, fontFamily: 'IBM Plex Mono, monospace' }}>
            {threat.status}
          </span>
        </div>
        <div
          style={{
            marginTop: 4,
            opacity: 0.75,
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: 11,
          }}
        >
          {threat.corroboration_count} {t('log.corroboration')} ·{' '}
          {Math.round(threat.confidence * 100)}% {t('log.confidence')}
        </div>
        {threat.has_conflict && (
          <div style={{ color: '#fb923c', fontWeight: 600, marginTop: 3 }}>
            ⚠ {t('log.conflict')}
          </div>
        )}
        {sources.length > 0 && (
          <div style={{ marginTop: 5, fontSize: 11, opacity: 0.6 }}>
            {sources.join(', ')}
          </div>
        )}
      </div>
    </Popup>
  )
}

function ThreatLayer({ threat }: { threat: Threat }) {
  const pts = trackPoints(threat)
  if (pts.length === 0) return null

  const color = threatColor(threat)
  const latlngs = pts.map((p) => [p.lat, p.lon] as [number, number])
  const head = pts[pts.length - 1]
  const heading = headingOf(threat)
  const active = !threat.closed_at

  return (
    <>
      {latlngs.length > 1 && (
        <Polyline
          // className is applied at creation only — remount when activity flips.
          key={`${threat.id}-${active ? 'live' : 'closed'}`}
          positions={latlngs}
          pathOptions={{
            color,
            weight: 3,
            opacity: active ? 0.8 : 0.45,
            className: active ? 'track-flow' : undefined,
            dashArray: !active && threat.has_conflict ? '6 6' : undefined,
          }}
        />
      )}
      {pts.slice(0, -1).map((p, i) => (
        <CircleMarker
          key={i}
          center={[p.lat, p.lon]}
          radius={3}
          pathOptions={{ color, fillColor: color, fillOpacity: 0.6, weight: 1 }}
        />
      ))}
      {/* Pulsing rings on the live head of an active track. */}
      {active && (
        <Marker
          position={[head.lat, head.lon]}
          icon={pulseIcon(color)}
          interactive={false}
          zIndexOffset={-100}
        />
      )}
      {heading != null ? (
        <Marker position={[head.lat, head.lon]} icon={arrowIcon(color, heading)}>
          <ThreatPopup threat={threat} />
        </Marker>
      ) : (
        <CircleMarker
          center={[head.lat, head.lon]}
          radius={7}
          pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 2 }}
        >
          <ThreatPopup threat={threat} />
        </CircleMarker>
      )}
    </>
  )
}

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
  const initialCenter: [number, number] = home ? [home.lat, home.lon] : KYIV_CENTER

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

        <HomeController />

        {home && (
          <>
            <Circle
              center={[home.lat, home.lon]}
              radius={home.radiusKm * 1000}
              pathOptions={{ color: '#38bdf8', fillColor: '#38bdf8', fillOpacity: 0.06, weight: 1 }}
            />
            <Marker position={[home.lat, home.lon]} icon={homeIcon}>
              <Tooltip direction="top" offset={[0, -18]}>
                {t('legend.home')} · {home.lat.toFixed(4)}, {home.lon.toFixed(4)}
              </Tooltip>
            </Marker>
          </>
        )}

        {Object.values(threats).map((th) => (
          <ThreatLayer key={th.id} threat={th} />
        ))}
      </MapContainer>
      <MapLegend />
    </div>
  )
}
