import { Building2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { useRadar } from '../../store'
import type { NotifyPrefs } from '../../store/notifySlice'
import { threatGlyphSvg } from '../../threatIcons'
import Switch from './Switch'

/** The prefs' type toggles reuse the map/feed glyph family — "Дрони" covers
 * both drone target types, so it wears the shahed glyph. */
const TYPES = [
  { key: 'ballistic', glyph: 'ballistic' },
  { key: 'missile', glyph: 'missile' },
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
    <div
      key={key}
      className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.03] px-2.5 py-2"
    >
      <div className="flex min-w-0 items-center gap-2.5">
        {icon}
        <div className="min-w-0">
          <div className="text-[13px] text-slate-300">{label}</div>
          {hint && <div className="mt-0.5 text-[11px] leading-snug text-slate-500">{hint}</div>}
        </div>
      </div>
      <Switch
        checked={Boolean(prefs[key])}
        onChange={(next) => setPrefs({ [key]: next })}
        label={label}
      />
    </div>
  )

  return (
    <div className="mt-2.5 space-y-2.5">
      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
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
                className={`w-full rounded-lg border px-3 py-2 text-left transition-colors duration-200 ${
                  active
                    ? 'border-phosphor/30 bg-phosphor/10'
                    : 'border-transparent bg-white/[0.03]'
                }`}
              >
                <span
                  className={`block text-[13px] font-medium ${
                    active ? 'text-phosphor-soft' : 'text-slate-300'
                  }`}
                >
                  {t(`notify.prefs.levels.${lvl}`)}
                </span>
                <span
                  className={`mt-0.5 block text-[11px] leading-snug ${
                    active ? 'text-slate-300' : 'text-slate-500'
                  }`}
                >
                  {t(`notify.prefs.levelHint.${lvl}`)}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
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
