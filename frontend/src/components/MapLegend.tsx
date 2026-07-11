import { ChevronDown, Layers } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { STATUS_COLORS } from '../theme'

const OPEN_KEY = 'klr-legend-open'

function initialOpen(): boolean {
  const saved = localStorage.getItem(OPEN_KEY)
  if (saved !== null) return saved === '1'
  // Default: open on desktop, collapsed on small screens.
  return window.matchMedia('(min-width: 1024px)').matches
}

/** Collapsible legend floating over the map (bottom-left, above leaflet UI). */
export default function MapLegend() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(initialOpen)

  const toggle = () => {
    localStorage.setItem(OPEN_KEY, open ? '0' : '1')
    setOpen(!open)
  }

  const rows: [string, string][] = [
    [STATUS_COLORS.confirmed, t('legend.confirmed')],
    [STATUS_COLORS.unconfirmed, t('legend.unconfirmed')],
    [STATUS_COLORS.impact, t('legend.impact')],
    [STATUS_COLORS.conflict, t('legend.conflict')],
    [STATUS_COLORS.destroyed, t('legend.destroyed')],
    ['#38bdf8', t('legend.home')],
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
            {rows.map(([color, label]) => (
              <li key={label} className="flex items-center gap-2 text-[11px] text-slate-300">
                <span
                  className="inline-block h-2.5 w-2.5 flex-none rounded-full"
                  style={{ background: color, boxShadow: `0 0 8px ${color}66` }}
                />
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
