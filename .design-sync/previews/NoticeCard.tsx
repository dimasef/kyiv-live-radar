import { NoticeCard } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'
import { notice } from './_fixtures'

const wrap = (n: ReturnType<typeof notice>[]) => (
  <Stage>
    <ul style={{ width: 300 }}>
      <NoticeCard notices={n} />
    </ul>
  </Stage>
)

export const AllClear = () => wrap([notice({ kind: 'clear' })])
export const Directional = () =>
  wrap([
    notice({
      kind: 'directional',
      text: 'Балістична загроза зі сходу — ймовірний курс на Київ. Прямуйте в укриття.',
      generated_by: 'llm',
      source_name: 'monitor',
    }),
  ])
export const Forecast = () =>
  wrap([
    notice({
      kind: 'forecast',
      text: 'Очікується повторний захід ударних БпЛА протягом найближчої години.',
      generated_by: 'llm',
    }),
  ])
export const MultiSource = () =>
  wrap([
    notice({ kind: 'summary', text: 'Підсумок: над містом працювала ППО, зафіксовано кілька груп «шахедів».', source_name: 'Київ ППО' }),
    notice({ id: 89, kind: 'summary', source_name: 'monitor' }),
  ])
