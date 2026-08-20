import { createPortal } from 'react-dom'

import { ZONE_GLOW } from './constants'

export const ZONE_GLOW_FILTER_ID = 'zone-inner-glow'

/** The SVG filter that turns an alert raion into a glowing outline.
 *
 * A raion under siren used to be a flat red wash. During a real raid most of the
 * oblast is alerted at once, so the map became one red sheet with the targets —
 * the thing it exists to show — floating on top of it. This paints the STATE at
 * the edges instead and leaves the middle clear.
 *
 * How it works: blur the shape's own alpha, then subtract that blur FROM the
 * alpha (`operator="out"`). Deep inside, the blur is opaque and the result
 * cancels to nothing; along the boundary it is only half-covered, so a band
 * survives and fades inward. Flooding that band with the alert colour leaves the
 * fill gone entirely — the filter's output is the glow, not the shape.
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
        <filter id={ZONE_GLOW_FILTER_ID} x="-5%" y="-5%" width="110%" height="110%">
          <feGaussianBlur in="SourceAlpha" stdDeviation={ZONE_GLOW.spreadPx} result="spread" />
          <feComposite in="SourceAlpha" in2="spread" operator="out" result="band" />
          <feFlood floodColor={ZONE_GLOW.color} floodOpacity={ZONE_GLOW.opacity} result="ink" />
          <feComposite in="ink" in2="band" operator="in" />
        </filter>
      </defs>
    </svg>,
    document.body,
  )
}
