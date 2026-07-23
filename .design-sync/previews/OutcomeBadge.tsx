import { OutcomeBadge } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

export const Matched = () => (
  <Stage><OutcomeBadge outcome="ціль" events={[{ threat_id: 42, event_id: 7 }]} noticeId={null} /></Stage>
)
export const MultiTrack = () => (
  <Stage>
    <OutcomeBadge
      outcome="ціль"
      events={[
        { threat_id: 42, event_id: 7 },
        { threat_id: 43, event_id: 8 },
      ]}
      noticeId={null}
    />
  </Stage>
)
export const Notice = () => <Stage><OutcomeBadge outcome="відбій" events={[]} noticeId={88} /></Stage>
export const Suppressed = () => <Stage><OutcomeBadge outcome="відсіяно" events={[]} noticeId={null} /></Stage>
