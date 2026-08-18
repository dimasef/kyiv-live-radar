import { ChevronDown, Layers } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { safeGet, safeSet, STORAGE_KEYS } from '../../lib/storage'
import { MUTED_COLOR, TYPE_COLORS } from '../../theme'
import { launcherGlyphSvg, threatGlyphSvg } from '../../threatIcons'
import type { TargetType } from '../../types'

function initialOpen(): boolean {
  const saved = safeGet(STORAGE_KEYS.legendOpen)
  if (saved !== null) return saved === '1'
  // Default: open on desktop, collapsed on small screens.
  return window.matchMedia('(min-width: 1024px)').matches
}

/** A 16px inline SVG (glyph or plain swatch) used for a legend row. */
function Swatch({
  html,
  faded = false,
  wide = false,
}: {
  html: string
  faded?: boolean
  // The group row carries a glyph AND its ×N chip, so it needs room the 16px
  // square doesn't have — without this the chip overlaps the label.
  wide?: boolean
}) {
  return (
    <span
      className={`inline-flex h-4 flex-none items-center justify-center ${wide ? 'w-8' : 'w-4'}`}
      style={faded ? { opacity: 0.3 } : undefined}
      aria-hidden
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

/** Collapsible legend floating over the map (bottom-left, above leaflet UI). */
export default function MapLegend() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(initialOpen)

  const toggle = () => {
    safeSet(STORAGE_KEYS.legendOpen, open ? '0' : '1')
    setOpen(!open)
  }

  // Type rows (colour = type, glyph = shape) + state rows (burst = hit, grey =
  // shot-down/lost). Homes are deliberately absent: the user picked their own
  // marker and labelled every contact's, so a legend entry explains nothing they
  // don't already know by looking.
  const types: TargetType[] = ['shahed', 'jet_drone', 'missile', 'ballistic']
  const rows: { html: string; label: string; faded?: boolean; wide?: boolean }[] = [
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
    // Without this row a faded marker reads as a rendering defect rather than as
    // "nobody has reported this one in a while".
    {
      html: threatGlyphSvg('shahed', { size: 16, color: TYPE_COLORS.shahed }),
      label: t('legend.quiet'),
      faded: true,
    },
    {
      html:
        threatGlyphSvg('shahed', { size: 16, color: TYPE_COLORS.shahed }) +
        '<span class="threat-count" style="position:static;margin-left:2px">\u00d73</span>',
      label: t('legend.group'),
      wide: true,
    },
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
            {rows.map(({ html, label, faded, wide }) => (
              <li key={label} className="flex items-center gap-2 text-[11px] text-slate-300">
                <Swatch html={html} faded={faded} wide={wide} />
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
