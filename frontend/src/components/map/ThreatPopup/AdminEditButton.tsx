import { Pencil } from 'lucide-react'

import { isAdminRole } from '@/api'
import { useRadar } from '@/store'
import type { Threat } from '@/types'

/** The way into the track editor, from the map itself.
 *
 * A wrong parse is SEEN here — the marker in the wrong place, carrying the
 * wrong type or an inflated count — and until now the repair lived on another
 * page: find the same message by its text in «Весь фід», open the track from
 * its chip. During a raid that hunt is the expensive half of the correction.
 *
 * A bare glyph riding the header line rather than a labelled button in a
 * section of its own: the popup is a reading surface for everyone, and an
 * admin affordance should cost it no height. The track number lives in the
 * tooltip, which is the only place that needs to spell it out. */
export default function AdminEditButton({ threat }: { threat: Threat }) {
  const isAdmin = useRadar((s) => isAdminRole(s.user?.role))
  const openAdminTrack = useRadar((s) => s.openAdminTrack)

  if (!isAdmin) return null

  return (
    <button
      onClick={() => openAdminTrack(threat.id)}
      title={`Редагувати трек T${threat.id}`}
      aria-label={`Редагувати трек T${threat.id}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 22,
        height: 22,
        padding: 0,
        border: 'none',
        borderRadius: 5,
        background: 'transparent',
        color: 'rgba(255,255,255,0.45)',
        cursor: 'pointer',
        alignSelf: 'center',
      }}
    >
      <Pencil size={13} />
    </button>
  )
}
