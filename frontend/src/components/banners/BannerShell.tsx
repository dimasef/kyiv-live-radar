import type { CSSProperties, ReactNode } from 'react'

import { PILL_CLASS, PILL_TONE } from './pillStyles'

export type BannerTone = 'attack' | 'alert' | 'clear'

export default function BannerShell({
  tone,
  color,
  role,
  label,
  expanded,
  onToggle,
  children,
}: {
  tone: BannerTone
  color: string
  role: 'alert' | 'status'
  label: string
  expanded: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const attack = tone === 'attack'

  return (
    <div role={role} className="pointer-events-none flex w-full justify-center">
      <button
        type="button"
        onClick={onToggle}
        aria-label={label}
        aria-expanded={expanded}
        className={`pointer-events-auto ${PILL_CLASS} ${attack ? '' : PILL_TONE[tone]}`}
        style={
          attack
            ? ({
                color,
                borderColor: `${color}66`,
                background: `${color}1f`,
                boxShadow: `0 0 22px -4px ${color}99`,
              } as CSSProperties)
            : undefined
        }
      >
        {children}
      </button>
    </div>
  )
}
