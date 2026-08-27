import { Info } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { safeGet, safeSet, STORAGE_KEYS } from '@/lib/storage'

import { mapControlClass } from '../controlStyles'
import { legendRows, type LegendRow } from './rows'
import SourceLinks from './SourceLinks'

function initialOpen(): boolean {
  const saved = safeGet(STORAGE_KEYS.legendOpen)
  if (saved !== null) return saved === '1'
  // Default: open on desktop, collapsed on small screens.
  return window.matchMedia('(min-width: 1024px)').matches
}

/** An inline SVG (glyph or swatch) used for a legend row. */
function Swatch({ html }: { html: string }) {
  return (
    <span
      className="inline-flex h-6 w-6 flex-none items-center justify-center"
      aria-hidden
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

/** A row of the legend. Where the thing has an opposite state, the row is a
 * button that flips to it — БПЛА ⇄ Збитий БПЛА, тривога ⇄ відбій — so the two
 * halves of every pair are learned in the space of one line instead of two.
 * A row with no opposite (the launch site) renders as plain text, with no hover
 * and no focus stop, so nothing invites a click that would do nothing. */
function Row({ row }: { row: LegendRow }) {
  const { t } = useTranslation()
  const [flipped, setFlipped] = useState(false)
  const shown = flipped && row.flipped ? row.flipped : row

  const content = (
    <>
      <Swatch html={shown.html} />
      <span className="truncate first-letter:uppercase">{t(shown.labelKey)}</span>
    </>
  )

  if (!row.flipped) {
    return <li className="flex items-center gap-2.5 px-1.5 py-1 text-[14px]">{content}</li>
  }
  return (
    <li>
      <button
        onClick={() => setFlipped(!flipped)}
        aria-pressed={flipped}
        className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1 text-left text-[14px] transition-colors hover:bg-white/[0.06]"
      >
        {content}
      </button>
    </li>
  )
}

/** Collapsible legend — what a marker's shape and colour mean. Positioned by
 * MapControls, not by itself. */
export default function MapLegend() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(initialOpen)

  const toggle = () => {
    safeSet(STORAGE_KEYS.legendOpen, open ? '0' : '1')
    setOpen(!open)
  }

  return (
    // The panel is a popover ABOVE the button, not a replacement for it. Opening
    // it used to swap a 40px chip for a 176px panel inside the control row, which
    // shoved the layer and fullscreen buttons sideways — the two things most
    // likely to be aimed at next moved out from under the cursor. Now the row
    // never changes width and the legend grows into the empty map above it.
    <div className="relative">
      <button
        onClick={toggle}
        aria-label={t(open ? 'legendCtl.hide' : 'legendCtl.show')}
        aria-expanded={open}
        className={mapControlClass(open)}
      >
        {/* Info, not Layers: the button opens reference — what a mark means and
            who reported it — while the button right next to it is the one that
            actually toggles a map LAYER. A stack-of-sheets glyph beside a real
            layer switch promises the wrong thing. */}
        <Info size={17} />
      </button>
      {open && (
        // Two separate cards in one anchored stack, sources on top. Scrollable
        // and height-capped because together they can outgrow the map above the
        // button on a short screen — the controls sit only ~4rem off the bottom
        // on mobile, and a panel running off the top edge is unreachable.
        <div className="scroll-slim absolute bottom-full left-0 mb-2 flex max-h-[68vh] w-64 flex-col gap-2 overflow-y-auto">
          <SourceLinks />
          <div className="panel popover-up p-3 text-slate-300">
            <span className="panel-title mb-2 block px-1.5">{t('legend.title')}</span>
            <ul className="space-y-0.5">
              {legendRows().map((row) => (
                // Keyed by id, not by label: the label changes when the row is
                // flipped, and a changing key would remount the row and snap it
                // straight back to its unflipped state.
                <Row key={row.id} row={row} />
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
