import { contactMarkerSvg } from '@/lib/contactMarker'

/** A small inline SVG of a contact's map marker — the row indicator, the profile
 * swatch, and each option in the marker-style picker all render through this. */
export default function MarkerGlyph({
  icon,
  color,
  size = 15,
}: {
  icon: string
  color: string
  size?: number
}) {
  return (
    <span
      aria-hidden
      className="inline-flex flex-none"
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: contactMarkerSvg(icon, color, size) }}
    />
  )
}
