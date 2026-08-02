import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { ContactStyle } from '@/lib/contactMarker'

import MarkerPreview from './MarkerPreview'
import MarkerStylePicker from './MarkerStylePicker'
import Overlay from './Overlay'

/** Pick how one home marker is drawn — the user's own (HomeMarkerRow, from the
 * settings drawer) or a contact's (ContactMapControls). One modal for both:
 * the choice is identical, only whose marker it is differs.
 *
 * It sits at Overlay's z-3000, above the settings drawer it can be opened from
 * (z-2000), so stacking over another surface works without special-casing. */
export default function MarkerStyleModal({
  title,
  caption,
  style,
  colors,
  onChange,
  onClose,
}: {
  title: string
  /** What the preview says the marker is for — whose map, whose home. */
  caption: string
  style: ContactStyle
  /** Overridable palette, so the user's own home can offer the cyan it
   * defaults to (see HOME_COLORS). */
  colors?: string[]
  onChange: (style: ContactStyle) => void
  onClose: () => void
}) {
  const { t } = useTranslation()

  return (
    <Overlay
      onClose={onClose}
      className="max-h-[90vh] w-full max-w-sm overflow-y-auto rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl sm:max-w-2xl sm:p-6"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <h2 className="min-w-0 truncate font-display text-base font-bold text-slate-100">
          {title}
        </h2>
        <button
          onClick={onClose}
          aria-label={t('panel.close')}
          className="flex-none text-slate-400 transition-colors hover:text-slate-100"
        >
          <X size={18} />
        </button>
      </div>

      <div className="space-y-3">
        <MarkerPreview style={style} caption={caption} />
        <MarkerStylePicker style={style} colors={colors} onChange={onChange} />
      </div>
    </Overlay>
  )
}
