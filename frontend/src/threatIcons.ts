// threatIcons.ts — сімейство гліфів загроз для Kyiv Live Radar
// Формат: один <path>, viewBox 0 0 24 24, fill підставляється в рантаймі.
// Директивні типи (shahed/jet_drone/missile) намальовані носом вгору (азимут 0°)
// і повертаються через rotate. ballistic/unknown — симетричні, не обертаються.
// КОЛІР = ТИП (див. theme.ts TYPE_COLORS): жовтий shahed, помаранч jet_drone,
// білий missile, фіолетовий ballistic. Збита/пропала → сіра (передається ззовні).

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
  // Нейтральний порожній ромб (fill-rule="evenodd")
  unknown: 'M12 3 L21 12 L12 21 L3 12 Z M12 7.6 L16.4 12 L12 16.4 L7.6 12 Z',
}

export const DIRECTIONAL: Record<TargetType, boolean> = {
  shahed: true,
  jet_drone: true,
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
}

/** Leaflet divIcon для мапи. Колір передається ззовні (тип, або сірий якщо збито). */
export function threatDivIcon(type: TargetType, opts: IconOpts = {}): L.DivIcon {
  const { state = 'active', bearingDeg = 0, color, size = 26 } = opts
  const html =
    state === 'fix'
      ? fixDotSvg(size, color)
      : threatGlyphSvg(type, { size, state, bearingDeg, color })
  return L.divIcon({
    html,
    className: 'threat-icon', // без дефолтних стилів leaflet
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}
