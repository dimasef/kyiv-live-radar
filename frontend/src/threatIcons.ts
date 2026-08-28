// threatIcons.ts — сімейство гліфів загроз для Kyiv Live Radar
// Формат: один <path>, viewBox 0 0 24 24, fill підставляється в рантаймі.
// Директивні типи (shahed/jet_drone/missile) намальовані носом вгору (азимут 0°)
// і повертаються через rotate. ballistic/unknown — симетричні, не обертаються.
// КОЛІР = ТИП (див. theme.ts TYPE_COLORS): жовтий shahed, помаранч jet_drone,
// білий missile, фіолетовий ballistic, бірюзовий fpv. Збита/пропала → сіра
// (передається ззовні).

import L from 'leaflet'

import { TYPE_COLORS } from './theme'
import type { TargetType } from './types'

// active = рухома голова треку (гліф, повертається за азимутом); fix = одиночна
// фіксація без напрямку (крапка); impact = влучання (гліф + спалах); destroyed =
// збита/пропала (гліф + перекреслення, колір сірий).
export type ThreatState = 'active' | 'fix' | 'impact' | 'destroyed'

export const THREAT_PATHS: Record<TargetType, string> = {
  // Дельта-крило з виступаючим носом і кілями на кінчиках (Shahed-136, вид зверху)
  shahed:
    'M12 1 C13.1 1 13.6 2 13.6 3.2 L13.6 6.4 L21.5 19 L22 22 L20.1 22 L19.6 19.8 L4.4 19.8 L3.9 22 L2 22 L2.5 19 L10.4 6.4 L10.4 3.2 C10.4 2 10.9 1 12 1 Z',
  // Той самий корпус + сопло двигуна за заднім краєм по центру
  jet_drone:
    'M12 1 C13.1 1 13.6 2 13.6 3.2 L13.6 6.4 L21.5 19 L22 22 L20.1 22 L19.6 19.8 L13.4 19.8 L13.4 22.8 L10.6 22.8 L10.6 19.8 L4.4 19.8 L3.9 22 L2 22 L2.5 19 L10.4 6.4 L10.4 3.2 C10.4 2 10.9 1 12 1 Z',
  // Тонкий фюзеляж, прямі крила посередині, малі стабілізатори (крилата, вид зверху)
  missile:
    'M12 1 C13 1.7 13.2 2.8 13.2 4 L13.2 9.8 L18.5 11.6 L18.5 13.2 L13.2 12.4 L13.2 16.8 L15.6 18.6 L15.6 20 L13.2 19.1 L13.2 21 C13.2 22.1 12.7 22.8 12 22.8 C11.3 22.8 10.8 22.1 10.8 21 L10.8 19.1 L8.4 20 L8.4 18.6 L10.8 16.8 L10.8 12.4 L5.5 13.2 L5.5 11.6 L10.8 9.8 L10.8 4 C10.8 2.8 11 1.7 12 1 Z',
  // Ракета конусом донизу (падіння згори), стабілізатори зверху; фіксована орієнтація, не обертається.
  // Фюзеляж навмисно ширший (+33% від центру), ніж інші гліфи — читається як
  // "товщий" силует, а не просто товщий обвід. Стабілізатори розведені
  // ширше пропорційно, щоб не злитись у товщому корпусі в одну пляму.
  ballistic:
    'M12 23 C13.1 21.5 14 19.8 14 18 L14 7 L17.5 4 L17.5 2.2 L14 3.8 L14 1 L10 1 L10 3.8 L6.5 2.2 L6.5 4 L10 7 L10 18 C10 19.8 10.9 21.5 12 23 Z',
  // Квадрокоптер згори: чотири ротори по кутах, X-рама, корпус по центру.
  // Силует навмисно не схожий на жоден інший — це єдиний тип, що читається
  // без кольору на 14px у стрічці.
  fpv:
    'M6.64 5.36 L18.64 17.36 L17.36 18.64 L5.36 6.64 Z '
    + 'M18.64 6.64 L6.64 18.64 L5.36 17.36 L17.36 5.36 Z '
    + 'M3.2 6 A2.8 2.8 0 1 0 8.8 6 A2.8 2.8 0 1 0 3.2 6 Z '
    + 'M15.2 6 A2.8 2.8 0 1 0 20.8 6 A2.8 2.8 0 1 0 15.2 6 Z '
    + 'M3.2 18 A2.8 2.8 0 1 0 8.8 18 A2.8 2.8 0 1 0 3.2 18 Z '
    + 'M15.2 18 A2.8 2.8 0 1 0 20.8 18 A2.8 2.8 0 1 0 15.2 18 Z '
    + 'M9.4 10.2 Q9.4 9.4 10.2 9.4 L13.8 9.4 Q14.6 9.4 14.6 10.2 L14.6 13.8 '
    + 'Q14.6 14.6 13.8 14.6 L10.2 14.6 Q9.4 14.6 9.4 13.8 Z',
  // Нейтральний порожній ромб (fill-rule="evenodd")
  unknown: 'M12 3 L21 12 L12 21 L3 12 Z M12 7.6 L16.4 12 L12 16.4 L7.6 12 Z',
}

// Whether a glyph ROTATES to its movement heading (only meaningful once the
// track has a vector). Drones and cruise missiles are oriented along travel;
// ballistic/unknown are fixed-orientation glyphs.
export const DIRECTIONAL: Record<TargetType, boolean> = {
  shahed: true,
  jet_drone: true,
  // A quadcopter seen from above is four-fold symmetric — rotating it changes
  // nothing on screen, so the rotation would only ever read as jitter.
  fpv: false,
  missile: true,
  ballistic: false,
  unknown: false,
}

// Whether a FIRST sighting with no heading yet renders as a plain fix dot
// (instead of the type glyph). A cruise-missile arrow is meaningless without a
// vector, so it stays a dot until it moves. Drones now show their glyph from
// the first point (pointing up until a course is known, then rotating);
// ballistic/unknown always show their glyph.
export const DOT_UNTIL_MOVING: Record<TargetType, boolean> = {
  shahed: false,
  jet_drone: false,
  fpv: false,
  missile: true,
  ballistic: false,
  unknown: false,
}


interface GlyphOpts {
  size?: number // px, мапна ~26, стрічкова ~14
  color?: string // fill; за замовчуванням — колір типу
  bearingDeg?: number // азимут руху; ігнорується для недирективних
  state?: ThreatState
}

/** Чистий SVG-рядок гліфа — для стрічки (inline) та для divIcon. */
export function threatGlyphSvg(type: TargetType, opts: GlyphOpts = {}): string {
  const { size = 26, state = 'active', bearingDeg = 0 } = opts
  const color = opts.color ?? TYPE_COLORS[type]
  const rot = DIRECTIONAL[type] ? bearingDeg : 0
  const fillRule = type === 'unknown' ? ' fill-rule="evenodd"' : ''

  let overlay = ''
  if (state === 'impact') {
    const rays = [0, 45, 90, 135, 180, 225, 270, 315]
      .map((a) => `<line x1="12" y1="-1" x2="12" y2="1.5" transform="rotate(${a} 12 12)"/>`)
      .join('')
    overlay = `<g stroke="${color}" stroke-width="1.6" stroke-linecap="round" opacity="0.9">${rays}</g>`
  }
  if (state === 'destroyed') {
    overlay =
      `<line x1="4" y1="20" x2="20" y2="4" stroke="#0a1a1f" stroke-width="4.5" stroke-linecap="round" opacity="0.6"/>` +
      `<line x1="4" y1="20" x2="20" y2="4" stroke="${color}" stroke-width="2.2" stroke-linecap="round"/>`
  }

  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="overflow:visible" xmlns="http://www.w3.org/2000/svg">` +
    `<g transform="rotate(${rot} 12 12)">` +
    `<path d="${THREAT_PATHS[type]}" fill="${color}" stroke="#000" stroke-width="0.7" stroke-linejoin="round"${fillRule}/>` +
    `</g>${overlay}</svg>`
  )
}

/** ОТРК / пусковий майданчик — гліф для origin-маркера БАЛІСТИЧНОЇ осі: ракета
 * зі стартовим факелом над лінією землі ("ось звідки пуск"). Балістику пускають з
 * наземного комплексу (Іскандер/КН-23), тож launch-зона не повинна малюватись
 * тим самим падаючим гліфом, що й ціль над містом. */
export function launcherGlyphSvg(opts: { size?: number; color?: string } = {}): string {
  const { size = 26 } = opts
  const color = opts.color ?? TYPE_COLORS.ballistic
  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="overflow:visible" xmlns="http://www.w3.org/2000/svg">` +
    // стартовий факел (напівпрозорий, донизу)
    `<path d="M10 12.2 L14 12.2 L12.7 15.5 L13.6 15.5 L12 19.2 L10.4 15.5 L11.3 15.5 Z" fill="${color}" opacity="0.6"/>` +
    // ракета носом угору
    `<path d="M12 2 C13.4 3.2 14 5 14 7 L14 12 L10 12 L10 7 C10 5 10.6 3.2 12 2 Z" fill="${color}" stroke="#000" stroke-width="0.7" stroke-linejoin="round"/>` +
    // стабілізатори
    `<path d="M10 9 L7.5 12 L10 12 Z M14 9 L16.5 12 L14 12 Z" fill="${color}" stroke="#000" stroke-width="0.7" stroke-linejoin="round"/>` +
    // лінія землі / пускова платформа
    `<line x1="5" y1="20.5" x2="19" y2="20.5" stroke="${color}" stroke-width="2" stroke-linecap="round"/>` +
    `</svg>`
  )
}

/** Крапка одиночної фіксації (директивний тип ще без вектора). */
export function fixDotSvg(size = 26, color = TYPE_COLORS.unknown): string {
  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">` +
    `<circle cx="12" cy="12" r="4" fill="${color}" stroke="#000" stroke-width="0.7"/>` +
    `<circle cx="12" cy="12" r="7.5" fill="none" stroke="${color}" stroke-width="1.2" opacity="0.4"/>` +
    `</svg>`
  )
}

interface IconOpts {
  state?: ThreatState
  bearingDeg?: number
  color?: string
  size?: number
  /** Stated group size. Spotters count targets constantly ("3 на Славутич"), and
   * a group of six used to look exactly like a single drone on the map — the
   * number was only in the popup and the feed. */
  count?: number | null
  /** The track just closed and is living out its linger — the icon fades away
   * over it instead of blinking out. A «Чисто» closes dozens of tracks in one
   * message, and dozens of markers vanishing on the same frame read as a glitch
   * rather than as an all-clear. */
  closing?: boolean
  /** Give the glyph its idle drift: a ~1px circular wander that says the contact
   * is live. It is deliberately CIRCULAR and sub-pixel-slow — a target's
   * position must never appear to change, and any straight-line motion would be
   * read as heading, which the glyph's rotation already means. Same condition as
   * the pulse rings (active and not quiet), so a target that stops being
   * reported goes still. */
  drift?: boolean
  /** Track id, used only to stagger the drift phase. Without it every marker
   * orbits in lockstep and the whole map appears to wobble as one. */
  seed?: number
}

/** Leaflet divIcon для мапи. Колір передається ззовні (тип, або сірий якщо збито). */
export function threatDivIcon(type: TargetType, opts: IconOpts = {}): L.DivIcon {
  const {
    state = 'active', bearingDeg = 0, color, size = 26, closing = false, count,
    drift = false, seed = 0,
  } = opts
  const raw =
    state === 'fix'
      ? fixDotSvg(size, color)
      : threatGlyphSvg(type, { size, state, bearingDeg, color })
  // Wrapped, never applied to the marker root: Leaflet owns that element's
  // transform (it is how the marker is positioned), so animating it there would
  // fight the map on every pan. The bearing rotation lives INSIDE the svg, so
  // the wrapper's transform is free.
  const glyph = drift
    ? `<span class="threat-drift" style="animation-delay:-${(seed % 36) / 10}s">${raw}</span>`
    : raw
  // Deliberately a SIBLING of the svg, never inside it: the glyph is rotated to
  // the movement heading, and a number inside that transform would hang upside
  // down on a southbound target. Neutral colours (never the type colour — a
  // yellow numeral on the yellow shahed glyph is unreadable), and
  // pointer-events:none so it can't swallow the click that opens the popup.
  const badge =
    count != null && count > 1 ? `<span class="threat-count">\u00d7${count}</span>` : ''
  return L.divIcon({
    html: glyph + badge,
    // без дефолтних стилів leaflet
    className: closing ? 'threat-icon threat-icon--closing' : 'threat-icon',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}
