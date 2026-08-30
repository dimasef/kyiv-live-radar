import { ADMIN_WIDTH } from './adminLayout'
import ActiveAlertList from './ActiveAlertList'
import ActiveIncidentList from './ActiveIncidentList'
import ActiveThreatList from './ActiveThreatList'
import DismissedList from './DismissedList'
import LlmStatsStrip from './LlmStatsStrip'

/** The manual-override console: cancel/retype/edit what the parser produced,
 * live. Reads active entities straight from the store (already hydrated + kept
 * fresh over WS); actions call /admin/* and the change echoes back over WS. */
export default function ManagementTab() {
  return (
    <div className={`${ADMIN_WIDTH} flex flex-col gap-6 px-4 py-4`}>
      <p className="text-xs text-slate-500">
        Ручне доналаштування розпізнавання: скасуйте хибну ціль/атаку/тривогу, змініть тип цілі або
        відредагуйте події. Зміни застосовуються миттєво для всіх клієнтів.
      </p>
      <LlmStatsStrip />
      <ActiveThreatList />
      <ActiveIncidentList />
      <ActiveAlertList />
      <DismissedList />
    </div>
  )
}
