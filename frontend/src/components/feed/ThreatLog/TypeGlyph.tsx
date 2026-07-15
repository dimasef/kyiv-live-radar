import { threatState } from '@/threatDisplay'
import { threatColor } from '@/theme'
import { threatGlyphSvg } from '@/threatIcons'
import type { Threat } from '@/types'

/** The target-type glyph for a feed row — same family as the map, small and
 * non-rotated (an icon, not a heading). Colour = type; grey once destroyed/lost;
 * a hit bursts. */
export default function TypeGlyph({ threat }: { threat: Threat }) {
  const svg = threatGlyphSvg(threat.target_type, {
    size: 15,
    state: threatState(threat),
    color: threatColor(threat),
  })
  return (
    <span
      className="inline-flex flex-none items-center"
      aria-hidden
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
