import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Friend } from '@/api'
import MarkerGlyph from '@/components/common/MarkerGlyph'
import MarkerStyleModal from '@/components/common/MarkerStyleModal'
import { contactStyleOf } from '@/lib/contactMarker'
import { useRadar } from '@/store'

import { personLabel } from './contactFormat'

const CHIP =
  'flex flex-none items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.03] p-1.5 transition-colors hover:border-white/20 hover:bg-white/[0.06]'

/** What one contact's shared home does on THIS user's map: the marker itself
 * (tap to restyle) and whether it shows at all — one click each, always visible
 * in their row rather than behind an edit mode. Two square chips of the same
 * shape, so neither reads as the more important one.
 *
 * Icon-only at every width, deliberately. Spelling the two out only fits by
 * giving them a second line on a phone, and that costs more than it buys: rows
 * stop having one shape, a floating right-aligned strip stops being obviously
 * attached to the name above it, and the labels end up louder than the person
 * they belong to.
 *
 * Both settings are private to the viewer: the contact is never told, and
 * hiding them here doesn't stop them sharing.
 *
 * A contact sharing no home gets the plain reason in the same slot. It is a
 * fact about them, not a control, so it never justified a click to reveal. */
export default function ContactMapControls({ friend }: { friend: Friend }) {
  const { t } = useTranslation()
  const toggleHome = useRadar((s) => s.toggleContactHome)
  const setStyle = useRadar((s) => s.setContactStyle)
  const hidden = useRadar((s) => s.hiddenHomeIds.includes(friend.id))
  const style = contactStyleOf(useRadar((s) => s.contactStyles[friend.id]))
  const [editing, setEditing] = useState(false)

  if (friend.home == null) {
    return <span className="text-[11px] text-slate-600">{t('friends.notSharing')}</span>
  }

  return (
    <>
      <button
        onClick={() => setEditing(true)}
        title={t('marker.edit')}
        aria-label={t('marker.edit')}
        className={`${CHIP} ${hidden ? 'opacity-50' : ''}`}
      >
        <MarkerGlyph icon={style.icon} color={style.color} size={18} glow={style.glow} />
      </button>

      {/* An eye rather than a bare switch: next to a marker, an unlabelled
          toggle could as easily mean notifications or sharing. The icon and its
          colour state which way it is, the tooltip says what pressing it does —
          and the marker beside it dims to say the same thing again. */}
      <button
        onClick={() => toggleHome(friend.id)}
        title={hidden ? t('friends.showOnMap') : t('friends.hideFromMap')}
        aria-label={hidden ? t('friends.showOnMap') : t('friends.hideFromMap')}
        aria-pressed={!hidden}
        className={`${CHIP} ${hidden ? 'text-slate-500' : 'text-phosphor-soft'}`}
      >
        {hidden ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>

      {editing && (
        <MarkerStyleModal
          title={personLabel(friend)}
          caption={t('marker.contactPreviewHint')}
          style={style}
          onChange={(s) => setStyle(friend.id, s)}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  )
}
