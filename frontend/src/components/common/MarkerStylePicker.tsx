import { useTranslation } from 'react-i18next'

import { CONTACT_COLORS, CONTACT_ICONS, type ContactStyle } from '@/lib/contactMarker'

import MarkerGlyph from './MarkerGlyph'
import Switch from './Switch'

/** Colour + shape picker for one home marker on the map — a contact's
 * (ContactMapControls) or the user's own (HomeMarkerRow). Both halves render
 * in the currently chosen colour, so the grid previews the pick before it's
 * made.
 *
 * The shape list is long enough to scroll; the swatches never do, because
 * losing sight of the colour while browsing shapes makes the grid unreadable.
 *
 * A wide screen gets bigger cells rather than more of them per row: these are
 * detailed little buildings, and at the phone's ~40px they are only just
 * readable. */
export default function MarkerStylePicker({
  style,
  colors = CONTACT_COLORS,
  onChange,
}: {
  style: ContactStyle
  /** Overridable so the user's own home can offer the cyan it defaults to. */
  colors?: string[]
  onChange: (style: ContactStyle) => void
}) {
  const { t } = useTranslation()

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.015] p-3">
      <div className="flex flex-wrap gap-2">
        {colors.map((color) => (
          <button
            key={color}
            onClick={() => onChange({ ...style, color })}
            aria-label={color}
            aria-pressed={color === style.color}
            className="relative h-7 w-7 flex-none rounded-full transition-transform hover:scale-105 sm:h-9 sm:w-9"
            style={{ background: color }}
          >
            {color === style.color && (
              <span
                className="absolute -inset-[3px] rounded-full border-2"
                style={{ borderColor: color }}
              />
            )}
          </button>
        ))}
      </div>

      <div className="mt-3 grid max-h-48 grid-cols-7 gap-1.5 overflow-y-auto sm:max-h-[24rem] sm:grid-cols-9 sm:gap-2">
        {CONTACT_ICONS.map((icon) => (
          <button
            key={icon.id}
            onClick={() => onChange({ ...style, icon: icon.id })}
            title={icon.label}
            aria-label={icon.label}
            aria-pressed={icon.id === style.icon}
            className={`relative flex aspect-square items-center justify-center rounded-lg border transition-colors ${
              icon.id === style.icon
                ? 'border-transparent bg-white/[0.07]'
                : 'border-white/[0.05] bg-white/[0.03] hover:bg-white/[0.08]'
            }`}
          >
            <MarkerGlyph
              icon={icon.id}
              color={style.color}
              size={34}
              glow={style.glow}
              className="h-[22px] w-[22px] sm:h-[34px] sm:w-[34px]"
            />
            {icon.id === style.icon && (
              <span
                className="pointer-events-none absolute -inset-px rounded-lg border-[1.5px]"
                style={{ borderColor: style.color, boxShadow: `0 0 12px -2px ${style.color}` }}
              />
            )}
          </button>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-white/[0.06] pt-3">
        <span className="text-[13px] text-slate-300">{t('marker.glow')}</span>
        <Switch
          checked={style.glow}
          label={t('marker.glow')}
          onChange={() => onChange({ ...style, glow: !style.glow })}
        />
      </div>
    </div>
  )
}
