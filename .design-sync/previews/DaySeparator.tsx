import { DaySeparator } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

export const Date = () => (
  <Stage>
    <ul style={{ width: 260 }}>
      <DaySeparator dayKey="2026-07-20" />
    </ul>
  </Stage>
)
export const EarlierDate = () => (
  <Stage>
    <ul style={{ width: 260 }}>
      <DaySeparator dayKey="2026-07-11" />
    </ul>
  </Stage>
)
