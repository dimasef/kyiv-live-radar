import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import MarkerGlyph from '@/components/common/MarkerGlyph'
import MarkerStyleModal from '@/components/common/MarkerStyleModal'
import { CONTACT_ICONS, HOME_COLORS, homeStyleOf } from '@/lib/contactMarker'
import { useRadar } from '@/store'

import SettingsRow from './SettingsRow'

/** How the user's own home marker is drawn — opened from the home section of
 * the settings drawer, where the rest of the home controls already live.
 *
 * Hidden without a home (there'd be no marker to style) and without an account:
 * the choice is stored on the account, so there is nowhere to remember it for
 * an anonymous visitor. Nothing picked here reaches contacts — they label this
 * same home themselves (see ContactMapControls).
 *
 * The colour only shows while nothing is threatening the home; MapView paints
 * the danger colours over it, which has to keep winning. */
export default function HomeMarkerRow() {
  const { t } = useTranslation()
  const authed = useRadar((s) => s.authStatus === 'authed')
  const home = useRadar((s) => s.home)
  const style = homeStyleOf(useRadar((s) => s.homeStyle))
  const setHomeStyle = useRadar((s) => s.setHomeStyle)
  const [editing, setEditing] = useState(false)

  if (!authed || !home) return null

  const shape = CONTACT_ICONS.find((i) => i.id === style.icon)?.label ?? ''

  return (
    <div className="mt-3">
      <SettingsRow
        icon={<MarkerGlyph icon={style.icon} color={style.color} size={18} glow={style.glow} />}
        label={t('marker.edit')}
        sub={shape}
        onClick={() => setEditing(true)}
      />
      {editing && (
        <MarkerStyleModal
          title={t('home.markerTitle')}
          caption={t('home.markerPreviewHint')}
          style={style}
          colors={HOME_COLORS}
          onChange={setHomeStyle}
          onClose={() => setEditing(false)}
        />
      )}
    </div>
  )
}
