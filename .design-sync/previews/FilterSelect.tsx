import { FilterSelect } from 'kyiv-live-radar-frontend'

import { Stage } from './_stage'

const options = [
  { value: 'all', label: 'Усі повідомлення' },
  { value: 'threat', label: 'Лише загрози' },
  { value: 'notice', label: 'Лише нотатки' },
  { value: 'suppressed', label: 'Відсіяні' },
]

export const Default = () => <Stage><FilterSelect options={options} value="all" onChange={() => {}} /></Stage>
export const Selected = () => <Stage><FilterSelect options={options} value="suppressed" onChange={() => {}} /></Stage>
