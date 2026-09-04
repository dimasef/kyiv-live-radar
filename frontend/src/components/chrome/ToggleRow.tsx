import type { ReactNode } from 'react'

import Switch from './Switch'

/** A yes/no setting: optional glyph, name, optional explanation, switch.
 *
 * Extracted once there were two of these — the notification prefs built it
 * inline and the map settings copied it — which is exactly how the seven
 * settings blocks drifted before `SettingsSection` pulled them together.
 *
 * The hint sits UNDER the whole row rather than beside the icon: it is a
 * sentence, and squeezing it into the space left over next to a switch made
 * the one row that had one (the city-wide push) wrap three times. It is also
 * unconditional — someone reading the drawer to decide needs the explanation
 * BEFORE they flip anything, which is precisely when a hint shown only in the
 * "off" state would be missing.
 */
export default function ToggleRow({
  title,
  hint,
  icon,
  checked,
  onChange,
  children,
}: {
  title: string
  hint?: string
  icon?: ReactNode
  checked: boolean
  onChange: (next: boolean) => void
  /** Settings that only mean anything while this one is on. */
  children?: ReactNode
}) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-2.5 py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          {icon}
          <div className="min-w-0 text-sm text-slate-300">{title}</div>
        </div>
        <Switch checked={checked} onChange={onChange} label={title} />
      </div>
      {hint && <p className="mt-0.5 text-sm leading-snug text-slate-500">{hint}</p>}
      {checked && children}
    </div>
  )
}
