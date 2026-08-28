import type L from 'leaflet'

/** Tag a GeoJSON layer's rendered paths so they can be focused and identified.
 *
 * Leaflet draws each polygon as a bare <svg:path>, which nothing can focus — so
 * on touch and on the TV remote, where there is no hover at all, a shape's name
 * was unreachable. A tabindex fixes all three input modes at once: it makes the
 * path a tab stop for a keyboard, a focus target for a remote, and (in every
 * browser we target) focused by a tap.
 *
 * Idempotent, because an inline ref callback re-runs on every render. It only
 * sets attributes — any focus listener is delegated on the map container by the
 * caller, so there is nothing here to attach twice or leak.
 *
 * `setAttribute`, not `dataset`: SVGElement.dataset is missing on the older
 * engines the TV target runs (see lib/observers for the same class of guard),
 * and there it would throw rather than degrade.
 */
export function tagPath(layer: L.GeoJSON | null, attr: string, id: string): void {
  layer?.eachLayer((child) => {
    const el = (child as L.Path).getElement?.()
    if (!el) return
    el.setAttribute('tabindex', '0')
    el.setAttribute(attr, id)
  })
}

/** The id a tagged path carries, or null for anything else on the map. */
export function taggedId(target: EventTarget | null, attr: string): string | null {
  const el = target as Element | null
  return el?.getAttribute?.(attr) ?? null
}
