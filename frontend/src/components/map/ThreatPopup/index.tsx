import type { CSSProperties } from 'react'
import { Popup } from 'react-leaflet'

import AnalyzeButton from '@/components/game/AnalyzeButton'
import { showsAnalyzeAffordance } from '@/components/game/analyzeButtonState'
import { isAdminRole } from '@/api'
import { useRadar } from '@/store'
import type { Threat } from '@/types'

import AdminEditButton from './AdminEditButton'
import DataSection from './DataSection'
import MessageList from './MessageList'
import MovementSection from './MovementSection'
import PopupHeader from './PopupHeader'
import { HAIRLINE, MONO } from './popupStyles'

/** What a target is, where it's going, and how much to trust that — in that
 * order, each in its own labelled section. A section with nothing to say
 * renders nothing at all, caption included. */
export default function ThreatPopup({ threat }: { threat: Threat }) {
  const gamification = useRadar((s) => s.gamification)
  const authed = useRadar((s) => s.authStatus === 'authed')
  const isAdmin = useRadar((s) => isAdminRole(s.user?.role))
  const analyze = gamification && showsAnalyzeAffordance(threat, authed)

  return (
    <Popup>
      {/* Width is fixed in index.css (.leaflet-popup-content), not here. */}
      <div style={{ fontSize: 13 } as CSSProperties}>
        <PopupHeader threat={threat} />
        <MovementSection threat={threat} />
        <DataSection threat={threat} />
        <MessageList threat={threat} />
        {/* The footer: what you can DO with this target, as opposed to what it
            is. Analysis on the left, the admin way into the track editor pinned
            right — the two are unrelated controls and sitting them apart is
            what stops the pencil reading as part of the analysis.

            The separator belongs to the row, not to the popup: a target with
            neither control renders no row at all, because drawing the rule
            regardless left a hairline hanging off the bottom edge with nothing
            under it. */}
        {(analyze || isAdmin) && (
          <div
            style={{
              marginTop: 8,
              paddingTop: 8,
              borderTop: `1px solid ${HAIRLINE}`,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            {analyze && <AnalyzeButton threat={threat} />}
            {/* marginLeft rather than `justifyContent: space-between`: with the
                analysis absent, space-between would leave the pencil on the
                left. */}
            {isAdmin && (
              <span style={{ marginLeft: 'auto', display: 'inline-flex' }}>
                <AdminEditButton threat={threat} />
              </span>
            )}
          </div>
        )}
        {import.meta.env.DEV && (
          <div style={{ marginTop: 4, fontSize: 10, opacity: 0.45, fontFamily: MONO }}>
            T{threat.id}
          </div>
        )}
      </div>
    </Popup>
  )
}
