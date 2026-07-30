import { CARD_PLATES } from './cardGlyphs'

/** The mock's duplicate badge, its exact styling, driven by the real count.
 * Injected into the plate (which is `position:relative`) so it sits top-right of
 * the glyph area, exactly like the design. */
function dupBadge(count: number): string {
  return (
    `<span style="position:absolute;top:9px;right:9px;z-index:3;display:inline-flex;` +
    `align-items:center;gap:2px;padding:3px 8px;border-radius:9px;background:rgba(6,9,13,.85);` +
    `border:1px solid var(--bd);font-family:'IBM Plex Mono',monospace;font-size:12px;` +
    `font-weight:600;letter-spacing:.02em;color:var(--rc);box-shadow:0 2px 10px -4px #000;">×${count}</span>`
  )
}

/** The injected 148px glyph plate for a card, prepared for rendering:
 * - replaces the mock's baked-in demo "×N" badge with one driven by the real
 *   `count` (dropped when the user has a single copy), and
 * - freezes the plate animations unless `animated` — so a grid tile sits still
 *   and only the popped-up card sweeps/pulses (incl. the "Кінець Війни" dawn).
 * The `var(--rc)/--tint/--glow/--bd` it references are set by the host CardView. */
export function cardPlateHtml(id: number, { animated, count }: { animated: boolean; count: number }): string {
  let html = (CARD_PLATES[id] ?? '').replace(/<span[^>]*>×\d+<\/span>/g, '')
  if (count > 1) html = html.replace(/(>)/, `$1${dupBadge(count)}`) // after the plate's opening tag
  if (!animated) html = html.replace(/animation:[^;"']*/g, 'animation:none')
  return html
}
