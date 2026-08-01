import type { ReactNode } from 'react'

export default function MenuItem({
  icon,
  children,
  onClick,
  danger,
  badge,
}: {
  icon: ReactNode
  children: ReactNode
  onClick: () => void
  danger?: boolean
  badge?: number
}) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 px-3.5 py-2.5 text-sm transition-colors ${
        danger ? 'text-red-300 hover:bg-red-400/[0.08]' : 'text-slate-300 hover:bg-white/[0.05] hover:text-slate-100'
      }`}
    >
      <span className="flex-none text-slate-500">{icon}</span>
      <span className="flex-1 text-left">{children}</span>
      {badge != null && badge > 0 && (
        <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white">
          {badge > 9 ? '9+' : badge}
        </span>
      )}
    </button>
  )
}
