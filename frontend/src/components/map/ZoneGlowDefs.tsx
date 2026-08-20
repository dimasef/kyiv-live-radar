import { createPortal } from 'react-dom'

import { ZONE_ALL_CLEAR, ZONE_GLOW } from './constants'

export const ZONE_GLOW_FILTER_ID = 'zone-inner-glow'
export const ZONE_ALL_CLEAR_FILTER_ID = 'zone-inner-glow-clear'

/** Blur the shape's own alpha, then subtract that blur FROM the alpha
 * (`operator="out"`). Deep inside, the blur is opaque and the result cancels to
 * nothing; along the boundary it is only half-covered, so a band survives and
 * fades inward. Flooding that band with a colour leaves the fill gone entirely —
 * the filter's output IS the glow, not the shape.
 *
 * Two instances of it exist, because an SVG filter cannot take a colour as a
 * parameter: red for a siren, green for the all-clear flash. */
function InnerGlow({
  id,
  color,
  opacity,
  spreadPx,
}: {
  id: string
  color: string
  opacity: number
  spreadPx: number
}) {
  return (
    <filter id={id} x="-5%" y="-5%" width="110%" height="110%">
      <feGaussianBlur in="SourceAlpha" stdDeviation={spreadPx} result="spread" />
      <feComposite in="SourceAlpha" in2="spread" operator="out" result="band" />
      <feFlood floodColor={color} floodOpacity={opacity} result="ink" />
      <feComposite in="ink" in2="band" operator="in" />
    </filter>
  )
}

/** The SVG filters that turn a raion into a glowing outline.
 *
 * A raion under siren used to be a flat red wash. During a real raid most of the
 * oblast is alerted at once, so the map became one red sheet with the targets —
 * the thing it exists to show — floating on top of it. This paints the STATE at
 * the edges instead and leaves the middle clear.
 *
 * Inward only, and that is the point: sirens cover neighbouring raions together,
 * and an outward glow would pile up on every shared border into exactly the red
 * smear this replaces.
 *
 * Portalled to <body> rather than rendered among the map's children: Leaflet
 * owns the DOM inside its panes, and `url(#id)` resolves per document anyway.
 * If a browser skips the filter entirely (the TV target is the one to worry
 * about), the separate border path still draws — the zone stays legible, it just
 * loses the glow. That is why the border is its own layer and not this filter's
 * job.
 */
export default function ZoneGlowDefs() {
  return createPortal(
    <svg
      aria-hidden
      focusable="false"
      width="0"
      height="0"
      style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden' }}
    >
      <defs>
        <InnerGlow
          id={ZONE_GLOW_FILTER_ID}
          color={ZONE_GLOW.color}
          opacity={ZONE_GLOW.opacity}
          spreadPx={ZONE_GLOW.spreadPx}
        />
        <InnerGlow
          id={ZONE_ALL_CLEAR_FILTER_ID}
          color={ZONE_ALL_CLEAR.color}
          opacity={ZONE_ALL_CLEAR.opacity}
          spreadPx={ZONE_ALL_CLEAR.spreadPx}
        />
      </defs>
    </svg>,
    document.body,
  )
}
