import { Building2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '@/store'
import type { NotifyPrefs } from '@/store/notifySlice'
import { threatGlyphSvg } from '@/threatIcons'
import ToggleRow from './ToggleRow'

/** The prefs' type toggles reuse the map/feed glyph family — "Дрони" covers
 * both drone target types, so it wears the shahed glyph. */
const TYPES = [
  { key: 'ballistic', glyph: 'ballistic' },
  { key: 'missile', glyph: 'missile' },
  { key: 'kab', glyph: 'kab' },
  { key: 'drone', glyph: 'shahed' },
] as const

function TypeIcon({ glyph }: { glyph: (typeof TYPES)[number]['glyph'] }) {
  return (
    <span
      className="inline-flex flex-none items-center"
      aria-hidden
      dangerouslySetInnerHTML={{ __html: threatGlyphSvg(glyph, { size: 15 }) }}
    />
  )
}

/** Phase-1 notification preferences, shown once pushes are ON: escalation
 * floor (radio cards with always-visible descriptions), target-type toggles
 * (map-family glyphs), and — separated, it's a scope rather than a type —
 * the city-wide alert push. Every change re-syncs the server subscription
 * (notifySlice). */
export default function NotifyPrefsControl() {
  const { t } = useTranslation()
  const prefs = useRadar((s) => s.notifyPrefs)
  const setPrefs = useRadar((s) => s.setNotifyPrefs)

  const toggleRow = (
    label: string,
    key: keyof NotifyPrefs,
    icon: React.ReactNode,
    hint?: string,
  ) => (
    <ToggleRow
      key={key}
      title={label}
      hint={hint}
      icon={icon}
      checked={Boolean(prefs[key])}
      onChange={(next) => setPrefs({ [key]: next })}
    />
  )

  return (
    <div className="mt-2.5 space-y-2.5">
      <div>
        <div className="mb-1.5 text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('notify.prefs.level')}
        </div>
        <div role="radiogroup" aria-label={t('notify.prefs.level')} className="space-y-1">
          {(['warning', 'danger'] as const).map((lvl) => {
            const active = prefs.minLevel === lvl
            return (
              <button
                key={lvl}
                role="radio"
                aria-checked={active}
                onClick={() => setPrefs({ minLevel: lvl })}
                className="opt opt--stack"
              >
                <span className="block text-sm">{t(`notify.prefs.levels.${lvl}`)}</span>
                <span className="opt-sub mt-0.5 block text-sm font-normal leading-snug">
                  {t(`notify.prefs.levelHint.${lvl}`)}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <div className="mb-1.5 text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('notify.prefs.types')}
        </div>
        <div className="space-y-1">
          {TYPES.map(({ key, glyph }) =>
            toggleRow(t(`notify.prefs.type.${key}`), key, <TypeIcon glyph={glyph} />),
          )}
        </div>
      </div>

      {toggleRow(
        t('notify.prefs.citywide'),
        'citywide',
        <Building2 size={15} className="flex-none text-slate-400" />,
        t('notify.prefs.citywideHint'),
      )}
    </div>
  )
}
