import { contactMarkerSvg } from '@/lib/contactMarker'

/** A small inline SVG of a home marker — the row indicator, the preview swatch,
 * and each option in the marker-style picker all render through this.
 *
 * `size` is the usual way to ask for one. Pass `className` instead when the box
 * has to be responsive (the picker's grid grows on a wide screen): the SVG then
 * stretches to whatever the class sizes the wrapper to, and `size` only decides
 * the markup's intrinsic size, which for a vector changes nothing on screen. */
export default function MarkerGlyph({
  icon,
  color,
  size = 15,
  glow = true,
  className,
}: {
  icon: string
  color: string
  size?: number
  glow?: boolean
  className?: string
}) {
  return (
    <span
      aria-hidden
      className={`inline-flex flex-none [&>svg]:h-full [&>svg]:w-full ${className ?? ''}`}
      style={className ? undefined : { width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: contactMarkerSvg(icon, color, size, glow) }}
    />
  )
}
