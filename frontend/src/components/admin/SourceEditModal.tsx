import { useState } from 'react'
import { createPortal } from 'react-dom'

import { updateSource, type Source } from '@/api'
import { useDismissTransition } from '@/lib/useDismissTransition'
import type { Region } from '@/types'

import { REGION_LABELS } from './sourceFormat'

/** Edit a source's name / role / region / trust_weight in a modal (mirrors
 * AuthModal's shell). trust_weight is shown only for spotter channels — it's
 * meaningless for alert channels (and inert everywhere, informational for now). */
export default function SourceEditModal({
  source,
  onSaved,
  onClose,
}: {
  source: Source
  onSaved: (s: Source) => void
  onClose: () => void
}) {
  const { shown, close } = useDismissTransition(onClose)
  const [name, setName] = useState(source.name)
  const [role, setRole] = useState<Source['role']>(source.role)
  const [region, setRegion] = useState<Region>(source.region)
  const [weight, setWeight] = useState(String(source.trust_weight))
  // Empty input = "leave on the server default" — the PATCH omits the field
  // rather than sending a 0, which would mean "never inherit" instead.
  const [inheritMinutes, setInheritMinutes] = useState(
    source.type_inherit_minutes === null ? '' : String(source.type_inherit_minutes),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  const save = async () => {
    setBusy(true)
    setError(false)
    try {
      const updated = await updateSource(source.id, {
        name: name.trim() || source.name,
        role,
        region,
        trust_weight: Number(weight),
        ...(inheritMinutes === '' ? {} : { type_inherit_minutes: Number(inheritMinutes) }),
      })
      onSaved(updated)
      close()
    } catch {
      setError(true)
      setBusy(false)
    }
  }

  const field = 'w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-100 focus:border-phosphor/40 focus:outline-none'

  return createPortal(
    <div
      className={`fixed inset-0 z-[2000] flex items-center justify-center bg-ink-950/80 p-4 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        className={`w-full max-w-sm rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl transition-all duration-200 ease-out ${
          shown ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-2 scale-95 opacity-0'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 font-display text-base font-bold text-slate-100">Редагувати джерело</h2>

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500">Назва</span>
            <input className={field} value={name} onChange={(e) => setName(e.target.value)} />
          </label>

          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500">Роль</span>
            <select className={field} value={role} onChange={(e) => setRole(e.target.value as Source['role'])}>
              <option value="spotter">spotter — канал спостерігачів</option>
              <option value="alert">alert — офіційні тривоги</option>
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-[11px] text-slate-500">
              Регіон — куди йдуть повідомлення без назви району («Відбій», «Чисто»)
            </span>
            <select
              className={field}
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
            >
              {Object.entries(REGION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          {role === 'spotter' && (
            <>
              <label className="block">
                <span className="mb-1 block text-[11px] text-slate-500">Вага довіри (інформативно, поки не впливає)</span>
                <input
                  className={field}
                  type="number"
                  step="0.1"
                  value={weight}
                  onChange={(e) => setWeight(e.target.value)}
                />
              </label>

              <label className="block">
                <span className="mb-1 block text-[11px] text-slate-500">
                  Успадкування типу, хв — скільки названий тут тип цілі типізує наступні
                  повідомлення з голим топонімом. Порожньо — типово; 0 — вимкнути.
                </span>
                <input
                  className={field}
                  type="number"
                  min="0"
                  max="120"
                  placeholder="типово"
                  value={inheritMinutes}
                  onChange={(e) => setInheritMinutes(e.target.value)}
                />
              </label>
            </>
          )}
        </div>

        {error && <p className="mt-3 text-xs text-rose-300">Не вдалося зберегти.</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={close}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-sm font-medium text-slate-300 hover:bg-white/[0.06]"
          >
            Скасувати
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="rounded-lg bg-phosphor px-3 py-1.5 text-sm font-semibold text-ink-950 hover:opacity-90 disabled:opacity-40"
          >
            {busy ? '…' : 'Зберегти'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
