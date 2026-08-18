import { useTranslation } from 'react-i18next'

import { JOURNAL_TABS, journalTabPath, navigate, type JournalTab } from '@/router'

/** Tab strip for the journal page. Each tab is its own route, so a reload or a
 * shared link opens the same view. */
export default function JournalTabs({ active }: { active: JournalTab }) {
  const { t } = useTranslation()
  return (
    <div className="mt-4 flex gap-1 border-b border-white/[0.06]">
      {JOURNAL_TABS.map((tab) => (
        <button
          key={tab}
          onClick={() => navigate(journalTabPath(tab))}
          aria-current={tab === active ? 'page' : undefined}
          className={`-mb-px rounded-t-md border-b-2 px-3 py-1.5 text-[13px] font-medium transition-colors ${
            tab === active
              ? 'border-phosphor text-slate-100'
              : 'border-transparent text-slate-500 hover:text-slate-300'
          }`}
        >
          {t(`journal.tabs.${tab}`)}
        </button>
      ))}
    </div>
  )
}
