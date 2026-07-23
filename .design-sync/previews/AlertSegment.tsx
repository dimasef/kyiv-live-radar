import { AlertSegment } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'
import { alert } from './_fixtures'

// AlertSegment inherits its text colour from the host banner (red while an
// alert is live); the running timer is now − started_at.
const NOW = Date.parse('2026-07-22T21:05:00Z')

export const City = () => (
  <Stage>
    <div className="text-red-200">
      <AlertSegment alert={alert({ scope: 'city', started_at: '2026-07-22T20:45:00Z' })} now={NOW} open compact={false} />
    </div>
  </Stage>
)
export const Oblast = () => (
  <Stage>
    <div className="text-red-200">
      <AlertSegment alert={alert({ scope: 'oblast', started_at: '2026-07-22T20:52:00Z' })} now={NOW} open compact={false} />
    </div>
  </Stage>
)
export const Compact = () => (
  <Stage>
    <div className="text-red-200">
      <AlertSegment alert={alert({ scope: 'city', started_at: '2026-07-22T20:45:00Z' })} now={NOW} open={false} compact />
    </div>
  </Stage>
)
