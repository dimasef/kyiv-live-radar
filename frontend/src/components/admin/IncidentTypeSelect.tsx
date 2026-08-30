import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { setIncidentType } from '@/api'
import type { Incident, TargetType } from '@/types'

import { ADMIN_TARGET_TYPES } from './adminLayout'

/** What is in the air, as the operator says it — or, by default, as derived from
 * the attack's member tracks.
 *
 * A multi-select rather than a dropdown because a raid is not always one thing:
 * naming two weapon families is how «комбінована» is said. That label is the
 * server's conclusion, not an option here — it appears once the chosen types
 * span two families, exactly as it does for an attack the system worked out on
 * its own.
 *
 * «Авто» is a real control and not just the starting state: the override is
 * stored, so without a way back the operator's first guess would own the attack
 * for the rest of the raid.
 *
 * Retyping the attack leaves the member tracks alone — each says what a spotter
 * reported over one district, the attack says what the raid is. Retyping one
 * track is a separate control, in «Активні цілі».
 */
export default function IncidentTypeSelect({ incident }: { incident: Incident }) {
  const { t } = useTranslation()
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState(false)
  const chosen = incident.type_override ?? []
  const manual = incident.type_override != null

  const apply = (types: TargetType[]) => {
    setPending(true)
    setFailed(false)
    setIncidentType(incident.id, types)
      .catch(() => setFailed(true))
      .finally(() => setPending(false))
  }

  const toggle = (tt: TargetType) =>
    apply(chosen.includes(tt) ? chosen.filter((x) => x !== tt) : [...chosen, tt])

  const chip = (active: boolean) =>
    `rounded px-1.5 py-0.5 text-[11px] leading-4 border transition-colors duration-150 disabled:opacity-40 ${
      active
        ? 'border-phosphor/40 bg-phosphor/15 text-phosphor-soft'
        : 'border-white/10 bg-white/[0.04] text-slate-400 hover:text-slate-200'
    }`

  return (
    <span className="flex flex-wrap items-center gap-1">
      <button
        type="button"
        disabled={pending}
        onClick={() => apply([])}
        title="Повернути тип, зведений з цілей атаки"
        className={chip(!manual)}
      >
        Авто
      </button>
      {ADMIN_TARGET_TYPES.map((tt) => (
        <button
          key={tt}
          type="button"
          disabled={pending}
          onClick={() => toggle(tt)}
          className={chip(chosen.includes(tt))}
        >
          {t(`target.${tt}`)}
        </button>
      ))}
      <span className={`ml-1 text-[11px] ${failed ? 'text-rose-300' : 'text-slate-500'}`}>
        {failed
          ? 'Помилка'
          : /* The server's conclusion, echoed back — the point of a multi-select
               is that «комбінована» is something the operator can now reach. */
            `→ ${t(`attack.classification.${incident.classification}`)}`}
      </span>
    </span>
  )
}
