import { ChevronDown, Layers } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { contactMarkerSvg, homeStyleOf } from '../../lib/contactMarker'
import { safeGet, safeSet, STORAGE_KEYS } from '../../lib/storage'
import { useRadar } from '../../store'
import { FRIEND_HOME_COLOR, MUTED_COLOR, TYPE_COLORS } from '../../theme'
import { launcherGlyphSvg, threatGlyphSvg } from '../../threatIcons'
import type { TargetType } from '../../types'

function initialOpen(): boolean {
  const saved = safeGet(STORAGE_KEYS.legendOpen)
  if (saved !== null) return saved === '1'
  // Default: open on desktop, collapsed on small screens.
  return window.matchMedia('(min-width: 1024px)').matches
}

/** A 16px inline SVG (glyph or plain swatch) used for a legend row. */
function Swatch({ html }: { html: string }) {
  return (
    <span
      className="inline-flex h-4 w-4 flex-none items-center justify-center"
      aria-hidden
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

// The friend row stands for every contact marker at once, so it stays on the
// default silhouette rather than picking one contact's chosen shape. The home
// row does follow the user's own pick — there is only ever one of those.
const friendSwatch = (color: string) => contactMarkerSvg('person', color, 16)

/** Collapsible legend floating over the map (bottom-left, above leaflet UI). */
export default function MapLegend() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(initialOpen)
  const hasFriendHomes = useRadar((s) =>
    s.friends.some((f) => f.home != null && !s.hiddenHomeIds.includes(f.id)),
  )
  const homeStyle = homeStyleOf(useRadar((s) => s.homeStyle))

  const toggle = () => {
    safeSet(STORAGE_KEYS.legendOpen, open ? '0' : '1')
    setOpen(!open)
  }

  // Type rows (colour = type, glyph = shape) + state rows (burst = hit, grey =
  // shot-down/lost) + home.
  const types: TargetType[] = ['shahed', 'jet_drone', 'missile', 'ballistic']
  const rows: { html: string; label: string }[] = [
    ...types.map((ty) => ({
      html: threatGlyphSvg(ty, { size: 16, color: TYPE_COLORS[ty] }),
      label: t(`target.${ty}`),
    })),
    {
      html: launcherGlyphSvg({ size: 16, color: TYPE_COLORS.ballistic }),
      label: t('legend.launcher'),
    },
    {
      html: threatGlyphSvg('unknown', { size: 16, state: 'destroyed', color: MUTED_COLOR }),
      label: t('legend.destroyed'),
    },
    { html: contactMarkerSvg(homeStyle.icon, homeStyle.color, 16, homeStyle.glow), label: t('legend.home') },
    ...(hasFriendHomes
      ? [{ html: friendSwatch(FRIEND_HOME_COLOR), label: t('legend.friend') }]
      : []),
  ]

  return (
    <div className="pointer-events-auto absolute bottom-[4.2rem] left-3 z-[900] lg:bottom-3">
      {open ? (
        <div className="panel w-44 p-3">
          <button
            onClick={toggle}
            aria-label={t('legendCtl.hide')}
            className="mb-2 flex w-full items-center justify-between text-left"
          >
            <span className="panel-title">{t('legend.title')}</span>
            <ChevronDown size={13} className="text-slate-500" />
          </button>
          <ul className="space-y-1.5">
            {rows.map(({ html, label }) => (
              <li key={label} className="flex items-center gap-2 text-[11px] text-slate-300">
                <Swatch html={html} />
                <span className="truncate">{label}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <button
          onClick={toggle}
          aria-label={t('legendCtl.show')}
          className="panel flex h-10 w-10 items-center justify-center text-slate-300 transition-colors duration-200 hover:text-phosphor-soft"
        >
          <Layers size={17} />
        </button>
      )}
    </div>
  )
}
