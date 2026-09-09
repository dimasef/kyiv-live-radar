import type { CSSProperties } from 'react'
import { Popup } from 'react-leaflet'

import type { Threat } from '@/types'

import DataSection from './DataSection'
import MessageList from './MessageList'
import MovementSection from './MovementSection'
import PopupFooter from './PopupFooter'
import PopupHeader from './PopupHeader'

/** What a target is, where it's going, and how much to trust that — in that
 * order, each in its own labelled section. A section with nothing to say
 * renders nothing at all, caption included. */
export default function ThreatPopup({ threat }: { threat: Threat }) {
  return (
    <Popup>
      {/* Width is fixed in index.css (.leaflet-popup-content), not here. */}
      <div style={{ fontSize: 13 } as CSSProperties}>
        <PopupHeader threat={threat} />
        <MovementSection threat={threat} />
        <DataSection threat={threat} />
        <MessageList threat={threat} />
        <PopupFooter threat={threat} />
      </div>
    </Popup>
  )
}
