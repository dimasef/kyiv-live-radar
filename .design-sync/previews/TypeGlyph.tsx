import { TypeGlyph } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'
import { threat } from './_fixtures'

export const Shahed = () => <Stage><TypeGlyph threat={threat({ target_type: 'shahed' })} /></Stage>
export const Ballistic = () => <Stage><TypeGlyph threat={threat({ target_type: 'ballistic' })} /></Stage>
export const Missile = () => <Stage><TypeGlyph threat={threat({ target_type: 'missile' })} /></Stage>
export const JetDrone = () => <Stage><TypeGlyph threat={threat({ target_type: 'jet_drone' })} /></Stage>
export const Destroyed = () => (
  <Stage>
    <TypeGlyph
      threat={threat({
        target_type: 'shahed',
        status: 'destroyed',
        closed_at: '2026-07-22T21:30:00Z',
        closed_reason: 'destroyed',
      })}
    />
  </Stage>
)
