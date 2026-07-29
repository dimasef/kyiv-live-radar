import type { CSSProperties } from 'react'

/** The per-card tactical glyph, transcribed from the Claude Design "Collectible
 * Cards" mock. Each uses `var(--rc)` (the rarity accent) for stroke/fill, so the
 * hosting CardView only needs to set that CSS var. `size` is the box in px; the
 * glow drop-shadow reads `var(--glow)` from the same host. */
export default function CardGlyph({ id, size = 70 }: { id: number; size?: number }) {
  const style: CSSProperties = {
    width: size,
    height: size,
    position: 'relative',
    filter: 'drop-shadow(0 0 8px var(--glow))',
  }
  const line = {
    fill: 'none',
    stroke: 'var(--rc)',
    strokeWidth: 1.5,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }

  switch (id) {
    case 1: // Тінь у небі — shahed silhouette among stars
      return (
        <svg viewBox="0 0 24 24" style={style}>
          <circle cx="4.5" cy="4" r=".7" fill="var(--rc)" opacity=".7" />
          <circle cx="20" cy="6" r=".6" fill="var(--rc)" opacity=".55" />
          <circle cx="18.5" cy="15.5" r=".6" fill="var(--rc)" opacity=".5" />
          <path
            d="M12 1 C13.1 1 13.6 2 13.6 3.2 L13.6 6.4 L21.5 19 L22 22 L20.1 22 L19.6 19.8 L4.4 19.8 L3.9 22 L2 22 L2.5 19 L10.4 6.4 L10.4 3.2 C10.4 2 10.9 1 12 1 Z"
            fill="var(--rc)"
          />
        </svg>
      )
    case 2: // Балістичний слід — streak lines + missile
      return (
        <svg viewBox="0 0 24 24" style={style}>
          <line x1="3" y1="2.5" x2="9" y2="10" stroke="var(--rc)" strokeWidth="1.4" strokeLinecap="round" opacity=".55" />
          <line x1="5.5" y1="2" x2="10" y2="8.5" stroke="var(--rc)" strokeWidth="1" strokeLinecap="round" opacity=".3" />
          <path
            d="M12 23 C13.1 21.5 14 19.8 14 18 L14 7 L17.5 4 L17.5 2.2 L14 3.8 L14 1 L10 1 L10 3.8 L6.5 2.2 L6.5 4 L10 7 L10 18 C10 19.8 10.9 21.5 12 23 Z"
            fill="var(--rc)"
          />
        </svg>
      )
    case 3: // Робота ППО — shield with check
      return (
        <svg viewBox="0 0 24 24" style={style} {...line}>
          <path d="M12 21s7-3.4 7-9V5l-7-3-7 3v7c0 5.6 7 9 7 9z" />
          <path d="m8.6 11.6 2.4 2.4 4.4-4.6" />
        </svg>
      )
    case 4: // Уламки на світанку — horizon with debris
      return (
        <svg viewBox="0 0 24 24" style={style}>
          <path d="M6 17.5a6 6 0 0 1 12 0" fill="none" stroke="var(--rc)" strokeWidth="1.2" opacity=".35" />
          <line x1="2.5" y1="17.5" x2="21.5" y2="17.5" stroke="var(--rc)" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M6 14.5 L7.4 17.5 L4.6 17.5 Z" fill="var(--rc)" />
          <path d="M12 12.8 L14 17.5 L10 17.5 Z" fill="var(--rc)" />
          <path d="M17.4 14.8 L18.7 17.5 L16.1 17.5 Z" fill="var(--rc)" />
        </svg>
      )
    case 5: // Відбій — dove / wave
      return (
        <svg viewBox="0 0 24 24" style={style} {...line}>
          <path d="M3 15 Q8 8 12 13 Q16 8 21 15" />
          <path d="M12 13 L12 17.5" opacity=".5" />
        </svg>
      )
    case 6: // Нічна зміна — crescent moon + stars
      return (
        <svg viewBox="0 0 24 24" style={style}>
          <path d="M18.2 13.8 A7 7 0 1 1 10.4 5.6 A5.4 5.4 0 0 0 18.2 13.8 Z" fill="none" stroke="var(--rc)" strokeWidth="1.5" strokeLinejoin="round" />
          <circle cx="16.4" cy="6" r=".75" fill="var(--rc)" />
          <circle cx="19.4" cy="9.4" r=".55" fill="var(--rc)" opacity=".7" />
        </svg>
      )
    case 7: // Купол — air-defence dome
      return (
        <svg viewBox="0 0 24 24" style={style} {...line}>
          <path d="M4 17a8 8 0 0 1 16 0" />
          <path d="M7 17a5 5 0 0 1 10 0" opacity=".4" />
          <line x1="2.5" y1="17" x2="21.5" y2="17" />
          <line x1="12" y1="9" x2="12" y2="5.6" opacity=".7" />
          <circle cx="12" cy="17" r=".9" fill="var(--rc)" stroke="none" />
        </svg>
      )
    case 8: // Мобільна група — searchlight + beams
      return (
        <svg viewBox="0 0 24 24" style={style} {...line}>
          <rect x="2.5" y="16" width="4.5" height="4.5" rx="1" />
          <path d="M7 16.4 L20 7.5" opacity=".85" />
          <path d="M7 20.1 L20 15.5" opacity=".85" />
          <path d="M20 7.5 L20 15.5" opacity=".35" />
          <circle cx="16" cy="11" r="1.5" fill="var(--rc)" stroke="none" />
        </svg>
      )
    case 9: // Ешелон — echelon of drones
      return (
        <svg viewBox="0 0 24 24" style={style} fill="var(--rc)">
          <path d="M12 3 L15 10 L9 10 Z" />
          <path d="M6 9 L8.6 15 L3.4 15 Z" opacity=".75" />
          <path d="M18 9 L20.6 15 L15.4 15 Z" opacity=".75" />
          <path d="M9.2 14 L11.4 19.5 L7 19.5 Z" opacity=".5" />
          <path d="M14.8 14 L17 19.5 L12.6 19.5 Z" opacity=".5" />
        </svg>
      )
    case 10: // Чисте небо — sun
      return (
        <svg viewBox="0 0 24 24" style={style} {...line}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2.4M12 18.6V21M3 12h2.4M18.6 12H21M5.6 5.6l1.7 1.7M16.7 16.7l1.7 1.7M18.4 5.6l-1.7 1.7M7.3 16.7l-1.7 1.7" />
        </svg>
      )
    default:
      return null
  }
}
