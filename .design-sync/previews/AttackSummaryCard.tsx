import { AttackSummaryCard } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'
import { incident } from './_fixtures'

const wrap = (i: ReturnType<typeof incident>) => (
  <Stage>
    <ul style={{ width: 300 }}>
      <AttackSummaryCard incident={i} />
    </ul>
  </Stage>
)

export const Combined = () => wrap(incident())
export const DroneOnly = () =>
  wrap(
    incident({
      classification: 'drone',
      target_type: 'shahed',
      has_hypersonic: false,
      decoy_suspected: false,
      impact_count: 0,
      track_count: 5,
      district_count: 3,
      attack_types: ['shahed'],
    }),
  )
export const Ballistic = () =>
  wrap(
    incident({
      classification: 'ballistic',
      target_type: 'ballistic',
      track_count: 2,
      impact_count: 1,
      district_count: 2,
      decoy_suspected: false,
    }),
  )
