import { Pencil } from 'lucide-react'

import { useRadar } from '@/store'
import { TYPE_COLORS } from '@/theme'
import type { Threat } from '@/types'

const ADMIN_VIOLET = TYPE_COLORS.ballistic

/** The way into the track editor, from the map itself.
 *
 * A wrong parse is SEEN here — the marker in the wrong place, carrying the
 * wrong type or an inflated count — and until now the repair lived on another
 * page: find the same message by its text in «Весь фід», open the track from
 * its chip. During a raid that hunt is the expensive half of the correction.
 *
 * A round violet chip sharing the footer line with the analysis affordance
 * rather than taking a section of its own: the popup is a reading surface for
 * everyone, and an admin control should cost it no height. The track number
 * lives in the tooltip, which is the only place that needs to spell it out.
 *
 * Violet is the palette's own (TYPE_COLORS.ballistic), and it is worn the way
 * the status chip wears its colour — a low-alpha wash under a lighter glyph —
 * rather than as flat ink. That is what keeps it a piece of chrome: a solid
 * #a855f7 mark inside a popup whose header may ALSO be #a855f7, because the
 * target is ballistic, would read as a second type signal.
 *
 * The role check is the CALLER's — the footer row only exists when there is
 * something to put in it, so one place has to answer "is this an admin" and
 * both have to agree. */
export default function AdminEditButton({ threat }: { threat: Threat }) {
  const openAdminTrack = useRadar((s) => s.openAdminTrack)

  return (
    <button
      onClick={() => openAdminTrack(threat.id)}
      title={`Редагувати трек T${threat.id}`}
      aria-label={`Редагувати трек T${threat.id}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 24,
        height: 24,
        padding: 0,
        borderRadius: '50%',
        border: `1px solid ${ADMIN_VIOLET}59`,
        background: `${ADMIN_VIOLET}26`,
        color: '#d8b4fe',
        cursor: 'pointer',
      }}
    >
      <Pencil size={12} />
    </button>
  )
}
