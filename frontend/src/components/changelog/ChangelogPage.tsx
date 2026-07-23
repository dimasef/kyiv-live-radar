import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { APP_VERSION, CHANGELOG, SEMVER_RULES, type BumpKind } from '../../changelog'

const KIND_COLOR: Record<BumpKind, string> = {
  major: '#f43f5e',
  minor: '#34d399',
  patch: '#54b8f0',
}

/** `2026-07-11` -> `11.07.2026`. */
function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

/** Standalone route (/change-log): version history + SemVer policy. A real page
 * so the URL can be shared. */
export default function ChangelogPage() {
  const { t } = useTranslation()
  const [rulesOpen, setRulesOpen] = useState(false)

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="mx-auto max-w-2xl px-5 py-6 sm:px-8 sm:py-10">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-lg font-bold tracking-wide text-slate-100">
            {t('changelog.title')}
          </h1>
          <span className="font-mono text-sm text-phosphor-soft">v{APP_VERSION}</span>
        </div>
        <p className="mt-1 text-[12px] text-slate-500">Kyiv Live Radar</p>

        {/* SemVer policy — collapsed by default */}
        <div className="mt-6 rounded-xl border border-white/[0.07] bg-white/[0.02]">
          <button
            onClick={() => setRulesOpen((v) => !v)}
            aria-expanded={rulesOpen}
            className="flex w-full items-center justify-between gap-2 p-4 text-left"
          >
            <span className="text-[10px] uppercase tracking-wider text-slate-500">
              {t('changelog.semverRules')}
            </span>
            <ChevronDown
              size={14}
              className={`flex-none text-slate-500 transition-transform duration-300 ${
                rulesOpen ? 'rotate-180' : ''
              }`}
            />
          </button>
          <div
            className={`grid transition-[grid-template-rows] duration-300 ease-out ${
              rulesOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
            }`}
          >
            <div className="overflow-hidden">
              <ul className="space-y-3 px-4 pb-4">
                {SEMVER_RULES.map((r) => (
                  <li key={r.part} className="flex gap-3">
                    <span className="mt-px w-14 flex-none font-mono text-[11px] font-semibold text-slate-300">
                      {r.part}
                    </span>
                    <span className="text-[12px] leading-relaxed text-slate-500">
                      <span className="text-slate-400">{r.label}.</span> {r.desc}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Releases */}
        <ul className="mt-7 space-y-6">
          {CHANGELOG.map((rel) => (
            <li key={rel.version}>
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <span className="font-mono text-[15px] font-semibold text-phosphor-soft">
                  v{rel.version}
                </span>
                <span className="text-[14px] font-medium text-slate-200">{rel.title}</span>
                <span className="ml-auto flex items-center gap-2.5">
                  <span className="font-mono text-[11px] text-slate-500">{formatDate(rel.date)}</span>
                  <span
                    className="rounded px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wide"
                    style={{ color: KIND_COLOR[rel.kind], background: `${KIND_COLOR[rel.kind]}1a` }}
                  >
                    {rel.kind}
                  </span>
                </span>
              </div>
              <ul className="mt-2.5 space-y-1.5">
                {rel.changes.map((c, i) => (
                  <li key={i} className="flex gap-2.5 text-[12.5px] leading-relaxed text-slate-400">
                    <span className="mt-2 h-1 w-1 flex-none rounded-full bg-slate-600" />
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
