import { StatusChip } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'
import { threat } from './_fixtures'

const closed = { closed_at: '2026-07-22T21:30:00Z' } as const

export const Destroyed = () => (
  <Stage><StatusChip threat={threat({ status: 'destroyed', ...closed, closed_reason: 'destroyed' })} /></Stage>
)
export const AllClear = () => (
  <Stage><StatusChip threat={threat({ status: 'lost', ...closed, closed_reason: 'all_clear' })} /></Stage>
)
export const Lost = () => (
  <Stage><StatusChip threat={threat({ status: 'lost', ...closed, closed_reason: 'stale' })} /></Stage>
)
export const Impact = () => (
  <Stage><StatusChip threat={threat({ status: 'impact', kind: 'impact' })} /></Stage>
)
