import { useState } from 'react'

import { isAdminRole } from '@/api'
import { AuthModal } from '@/components/auth'
import { RawMessagesView } from '@/components/raw'
import { adminTabFromPath, adminTabPath, navigate, useRoute } from '@/router'
import { useRadar } from '@/store'

import BugReportsPanel from './BugReportsPanel'
import CorrectionsPanel from './CorrectionsPanel'
import CoverageGapList from './CoverageGapList'
import ManagementTab from './ManagementTab'
import ReprocessPanel from './ReprocessPanel'
import SourcesPanel from './SourcesPanel'

/** Admin console (replaces the old standalone /raw tab). Gates on admin exactly
 * like the former RawMessagesPage did — the backend also enforces it (401/403),
 * so this is UX only. Non-admins never mount the data views. The open tab is
 * driven by the URL (/admin/<tab>) so a reload keeps it instead of resetting. */
export default function AdminPage() {
  const status = useRadar((s) => s.authStatus)
  const isAdmin = useRadar((s) => isAdminRole(s.user?.role))
  const tab = adminTabFromPath(useRoute())
  const [loginOpen, setLoginOpen] = useState(false)

  if (status === 'unknown') {
    return (
      <div className="flex h-full items-center justify-center bg-ink-950 text-xs text-slate-500">
        Завантаження…
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-ink-950 px-4 text-center text-slate-300">
        <p className="max-w-xs text-sm text-slate-400">
          {status === 'authed'
            ? 'Ця сторінка доступна лише адміністраторам.'
            : 'Увійдіть як адміністратор, щоб відкрити адмінку.'}
        </p>
        {status !== 'authed' && (
          <button
            onClick={() => setLoginOpen(true)}
            className="rounded-lg bg-phosphor px-4 py-2 text-sm font-semibold text-ink-950 hover:opacity-90"
          >
            Увійти
          </button>
        )}
        {loginOpen && <AuthModal onClose={() => setLoginOpen(false)} />}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-ink-950 text-slate-200">
      <div className="shrink-0 border-b border-white/[0.06] px-4 pt-6 pb-0">
        <div className="mx-auto max-w-3xl">
          <h1 className="font-display text-lg font-bold text-slate-100">Адмінка</h1>
          <div className="mt-3 flex flex-wrap gap-1">
            <TabButton active={tab === 'manage'} onClick={() => navigate(adminTabPath('manage'))}>
              Керування
            </TabButton>
            <TabButton active={tab === 'bugs'} onClick={() => navigate(adminTabPath('bugs'))}>
              Баги
            </TabButton>
            <TabButton active={tab === 'sources'} onClick={() => navigate(adminTabPath('sources'))}>
              Джерела
            </TabButton>
            <TabButton active={tab === 'gaps'} onClick={() => navigate(adminTabPath('gaps'))}>
              Прогалини
            </TabButton>
            <TabButton
              active={tab === 'corrections'}
              onClick={() => navigate(adminTabPath('corrections'))}
            >
              Виправлення
            </TabButton>
            <TabButton
              active={tab === 'reprocess'}
              onClick={() => navigate(adminTabPath('reprocess'))}
            >
              Перебудова
            </TabButton>
            <TabButton active={tab === 'raw'} onClick={() => navigate(adminTabPath('raw'))}>
              Весь Фід
            </TabButton>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {tab === 'raw' ? (
          <RawMessagesView />
        ) : (
          <div className="h-full overflow-y-auto overscroll-contain">
            {tab === 'manage' && <ManagementTab />}
            {tab === 'bugs' && <BugReportsPanel />}
            {tab === 'sources' && <SourcesPanel />}
            {tab === 'gaps' && <CoverageGapList />}
            {tab === 'corrections' && <CorrectionsPanel />}
            {tab === 'reprocess' && <ReprocessPanel />}
          </div>
        )}
      </div>
    </div>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px rounded-t-md border-b-2 px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? 'border-phosphor text-slate-100'
          : 'border-transparent text-slate-500 hover:text-slate-300'
      }`}
    >
      {children}
    </button>
  )
}
