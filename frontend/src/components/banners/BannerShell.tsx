import type { CSSProperties, ReactNode } from 'react'

export type BannerTone = 'attack' | 'alert' | 'clear'

const TONE_CLASS: Record<Exclude<BannerTone, 'attack'>, string> = {
  alert: 'border-red-400/40 bg-red-500/15 text-red-200 shadow-[0_0_22px_-4px_rgba(239,68,68,0.6)]',
  clear:
    'border-emerald-400/30 bg-emerald-500/10 text-emerald-300 shadow-[0_0_22px_-4px_rgba(16,185,129,0.5)]',
}

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
        className={`pointer-events-auto flex max-w-full items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-2 text-[11.5px] font-semibold backdrop-blur-md sm:gap-2.5 sm:text-[13px] ${
          attack ? '' : TONE_CLASS[tone]
        }`}
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
