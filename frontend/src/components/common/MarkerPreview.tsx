import { CONTACT_ICONS, type ContactStyle } from '@/lib/contactMarker'

import MarkerGlyph from './MarkerGlyph'

/** The chosen marker shown the way the map draws it — glowing, on grid paper —
 * so the pick can be judged against a dark background rather than against the
 * panel it was made in. */
export default function MarkerPreview({
  style,
  caption,
}: {
  style: ContactStyle
  caption: string
}) {
  const label = CONTACT_ICONS.find((i) => i.id === style.icon)?.label ?? ''

  return (
    <div
      className="flex items-center gap-4 rounded-2xl border border-white/[0.07] bg-ink-950 p-4"
      style={{
        backgroundImage: `linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px)`,
        backgroundSize: '28px 28px',
      }}
    >
      <span className="relative flex h-14 w-14 flex-none items-center justify-center">
        <span
          className="absolute inset-0 rounded-full border-[1.5px]"
          style={{
            background: `${style.color}1f`,
            borderColor: `${style.color}66`,
            boxShadow: style.glow ? `0 0 22px -6px ${style.color}` : 'none',
          }}
        />
        <MarkerGlyph icon={style.icon} color={style.color} size={28} glow={style.glow} />
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-slate-200">{label}</p>
        <p className="mt-0.5 text-[11px] leading-snug text-slate-500">{caption}</p>
      </div>
    </div>
  )
}
