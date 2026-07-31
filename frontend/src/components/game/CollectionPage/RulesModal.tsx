import { X } from 'lucide-react'

import Overlay from '@/components/common/Overlay'

/** How cards are earned — shown from the collection info button. */
const RULES = [
  'Увімкни «Гейміфікацію» в налаштуваннях (потрібен вхід в акаунт).',
  'На карті клікни ціль — БПЛА, ракету або балістику.',
  'Натисни «Аналіз», поки ціль у польоті, або «Аналіз рештків», коли її збили чи загубили.',
  'Сканування триває кілька секунд — і ти отримуєш випадкову картку.',
  'З однієї цілі можна зробити 2 аналізи (політ + рештки). Перший, хто встиг, забирає картку.',
  'Цілі, старші за 12 годин, аналізувати вже не можна.',
]

export default function RulesModal({ onClose }: { onClose: () => void }) {
  return (
    <Overlay onClose={onClose} className="rise w-full max-w-sm rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-display text-sm font-bold text-slate-100">Як отримати картки</h3>
        <button onClick={onClose} aria-label="Закрити" className="text-slate-400 hover:text-slate-100">
          <X size={18} />
        </button>
      </div>
      <ol className="flex list-decimal flex-col gap-2 pl-4 text-[13px] leading-relaxed text-slate-300 marker:font-mono marker:text-slate-600">
        {RULES.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ol>
    </Overlay>
  )
}
