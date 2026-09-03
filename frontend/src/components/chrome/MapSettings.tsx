import { Radar } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import { TRACK_WIDTH_MAX, TRACK_WIDTH_MIN, type MapMarkerSize } from '@/store/prefsSlice'

import SettingsSection from './SettingsSection'
import Switch from './Switch'

const SIZES: MapMarkerSize[] = ['sm', 'md', 'lg']

// Chrome comes from `.opt`, which reads the lit state off `aria-pressed`.
const seg = 'opt flex-1 text-sm'
const label = 'mb-1 block text-sm text-slate-500'

/** A yes/no setting: name, always-visible explanation of what it does, switch.
 * The hint is not conditional — someone reading the drawer to decide needs it
 * BEFORE they flip anything, which is exactly when it would be hidden. */
function ToggleRow({
  title,
  hint,
  checked,
  onChange,
  children,
}: {
  title: string
  hint: string
  checked: boolean
  onChange: (next: boolean) => void
  /** Settings that only mean anything while this is on. */
  children?: ReactNode
}) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-2.5 py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm text-slate-300">{title}</div>
        <Switch checked={checked} onChange={onChange} label={title} />
      </div>
      <p className="mt-0.5 text-sm leading-snug text-slate-500">{hint}</p>
      {checked && children}
    </div>
  )
}

/** How the map draws targets: whether a trail follows one, how heavy it is,
 * how big the target itself is, and whether any of it moves.
 *
 * Per-device, not per-account (see prefsSlice): the same person reads this map
 * on a phone in a corridor and on a TV across a room, and those want different
 * answers. Nothing here changes what is KNOWN — only what is drawn. */
export default function MapSettings() {
  const { t } = useTranslation()
  const mapTrail = useRadar((s) => s.mapTrail)
  const setMapTrail = useRadar((s) => s.setMapTrail)
  const mapTrackWidth = useRadar((s) => s.mapTrackWidth)
  const setMapTrackWidth = useRadar((s) => s.setMapTrackWidth)
  const mapMarkerSize = useRadar((s) => s.mapMarkerSize)
  const setMapMarkerSize = useRadar((s) => s.setMapMarkerSize)
  const mapMotion = useRadar((s) => s.mapMotion)
  const setMapMotion = useRadar((s) => s.setMapMotion)

  return (
    <SettingsSection icon={Radar} title={t('settings.map')}>
      <div className="space-y-2.5">
        <ToggleRow
          title={t('settings.mapTrail')}
          hint={t('settings.mapTrailHint')}
          checked={mapTrail}
          onChange={setMapTrail}
        >
          {/* Thickness is meaningless with no line to thicken, so it only
              exists while the trail does. The value is shown as a SAMPLE of
              the line it sets rather than as a number — "5" says nothing about
              how a track will read across a map. */}
          <label className="mt-3 flex items-center justify-between gap-3 text-sm text-slate-500">
            <span>{t('settings.mapTrackWidth')}</span>
            <span
              aria-hidden
              className="w-8 flex-none rounded-full bg-phosphor-soft"
              style={{ height: mapTrackWidth }}
            />
          </label>
          <input
            type="range"
            min={TRACK_WIDTH_MIN}
            max={TRACK_WIDTH_MAX}
            step={1}
            value={mapTrackWidth}
            onChange={(e) => setMapTrackWidth(Number(e.target.value))}
            aria-label={t('settings.mapTrackWidth')}
            className="range-glow mt-2"
            style={
              {
                '--fill': `${
                  ((mapTrackWidth - TRACK_WIDTH_MIN) / (TRACK_WIDTH_MAX - TRACK_WIDTH_MIN)) * 100
                }%`,
              } as CSSProperties
            }
          />
        </ToggleRow>

        <ToggleRow
          title={t('settings.mapMotion')}
          hint={t('settings.mapMotionHint')}
          checked={mapMotion}
          onChange={setMapMotion}
        />

        <div>
          <span className={label}>{t('settings.mapMarkers')}</span>
          <div className="flex gap-1">
            {SIZES.map((o) => (
              <button
                key={o}
                onClick={() => setMapMarkerSize(o)}
                aria-pressed={mapMarkerSize === o}
                className={seg}
              >
                {t(`settings.marker.${o}`)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </SettingsSection>
  )
}
