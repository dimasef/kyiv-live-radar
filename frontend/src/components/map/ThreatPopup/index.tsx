import type { CSSProperties } from 'react'
import { Popup } from 'react-leaflet'

import AnalyzeButton from '@/components/game/AnalyzeButton'
import { showsAnalyzeAffordance } from '@/components/game/analyzeButtonState'
import { useRadar } from '@/store'
import type { Threat } from '@/types'

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

  return (
    <Popup>
      {/* Width is fixed in index.css (.leaflet-popup-content), not here. */}
      <div style={{ fontSize: 13 } as CSSProperties}>
        <PopupHeader threat={threat} />
        <MovementSection threat={threat} />
        <DataSection threat={threat} />
        <MessageList threat={threat} />
        {/* The separator belongs to the button, not to the popup: this section
            renders nothing for a target with no analysis to offer, and drawing
            the rule regardless left a hairline hanging off the bottom edge with
            nothing under it. */}
        {gamification && showsAnalyzeAffordance(threat, authed) && (
          <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${HAIRLINE}` }}>
            <AnalyzeButton threat={threat} />
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
