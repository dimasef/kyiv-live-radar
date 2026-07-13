import { useTranslation } from 'react-i18next'

import { setLanguage } from '../../i18n'

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const langs = ['uk', 'en']
  return (
    <div className="flex rounded-full border border-white/10 bg-white/[0.04] p-0.5 text-[11px] font-mono">
      {langs.map((l) => {
        const active = i18n.language.startsWith(l)
        return (
          <button
            key={l}
            onClick={() => setLanguage(l)}
            className={`rounded-full px-2.5 py-1 uppercase tracking-wider transition-all duration-200 ${
              active
                ? 'bg-phosphor/15 text-phosphor-soft shadow-[0_0_10px_-2px_rgba(34,211,238,0.5)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {l}
          </button>
        )
      })}
    </div>
  )
}
