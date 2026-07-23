import { CalendarHeatmap } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'
import { heatmapDays } from './_fixtures'

// July 2026 (month0 = 6): a spread of intensities, two ballistic days flagged
// with a violet dot, one selected day and today ringed.
export const July = () => (
  <Stage>
    <div style={{ width: 300 }}>
      <CalendarHeatmap
        year={2026}
        month0={6}
        daysByDate={heatmapDays()}
        selectedDate="2026-07-18"
        today="2026-07-22"
        locale="uk"
        onSelect={() => {}}
      />
    </div>
  </Stage>
)
