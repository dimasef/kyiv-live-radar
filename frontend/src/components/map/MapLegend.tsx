import { ChevronDown, Layers } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { safeGet, safeSet, STORAGE_KEYS } from '../../lib/storage'
import { useRadar } from '../../store'
import { MUTED_COLOR, TYPE_COLORS } from '../../theme'
import { launcherGlyphSvg, threatGlyphSvg } from '../../threatIcons'
import type { TargetType } from '../../types'
import { ZONE_STYLES } from './constants'

function initialOpen(): boolean {
  const saved = safeGet(STORAGE_KEYS.legendOpen)
  if (saved !== null) return saved === '1'
  // Default: open on desktop, collapsed on small screens.
  return window.matchMedia('(min-width: 1024px)').matches
}

/** A filled square in a zone tone — the alert layer paints areas, not markers,
 * so its legend rows can't reuse the threat glyphs. */
function zoneSwatch(style: { color: string; fillColor: string; dashArray?: string }): string {
  const dash = style.dashArray ? ` stroke-dasharray="${style.dashArray}"` : ''
  return (
    `<svg width="16" height="16" viewBox="0 0 16 16">` +
    `<rect x="2.5" y="2.5" width="11" height="11" rx="1.5" fill="${style.fillColor}" ` +
    `fill-opacity="0.35" stroke="${style.color}"${dash}/></svg>`
  )
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

/** Collapsible legend — what a marker's shape and colour mean. Positioned by
 * MapControls, not by itself. */
export default function MapLegend() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(initialOpen)
  const zoneLayerOn = useRadar((s) => s.zoneLayerOn)

  const toggle = () => {
    safeSet(STORAGE_KEYS.legendOpen, open ? '0' : '1')
    setOpen(!open)
  }

  // Type rows (colour = type, glyph = shape) + state rows (burst = hit, grey =
  // shot-down/lost). Homes are deliberately absent: the user picked their own
  // marker and labelled every contact's, so a legend entry explains nothing they
  // don't already know by looking.
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
  ]
  // The raion-alert layer has its own visual language (a filled area, not a
  // marker), so its rows only appear while it is switched on.
  if (zoneLayerOn) {
    rows.push(
      { html: zoneSwatch(ZONE_STYLES.alert), label: t('zones.alert') },
      { html: zoneSwatch(ZONE_STYLES.clear), label: t('zones.clear') },
      { html: zoneSwatch(ZONE_STYLES.stale), label: t('zones.noData') },
    )
  }

  return (
    <>
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
    </>
  )
}
