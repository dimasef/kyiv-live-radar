import { AlertTriangle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import {
  applyReprocess,
  fetchReprocessPreview,
  type ReprocessPreview,
  type ReprocessResult,
} from '@/api'

import ReprocessDiff from './ReprocessDiff'
import ReprocessScope, { DEFAULT_LAST } from './ReprocessScope'

const SCOPE_DEBOUNCE_MS = 300

/** Rebuild tracks/incidents from stored raw messages through the current
 * parser — the safe replacement for the REPROCESS_ON_BOOT env+restart dance.
 * Shows the scope up front, warns if an attack is active, and reports a
 * before/after diff. The apply runs server-side under the ingest lock.
 *
 * Defaults to the last few hundred messages rather than the whole log: a parser
 * fix is judged on the stretch still visible on the map, and rebuilding months
 * of history to see it is slow and needlessly destructive. */
export default function ReprocessPanel() {
  const [preview, setPreview] = useState<ReprocessPreview | null>(null)
  const [last, setLast] = useState<number | null>(DEFAULT_LAST)
  // Debounced copy — typing "300" must not fire a preview per keystroke.
  const [scope, setScope] = useState<number | null>(DEFAULT_LAST)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<ReprocessResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setScope(last), SCOPE_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [last])

  const loadPreview = useCallback(() => {
    fetchReprocessPreview(scope ?? undefined)
      .then(setPreview)
      .catch(() => setError('Не вдалося завантажити огляд'))
  }, [scope])
  useEffect(loadPreview, [loadPreview])

  const run = async () => {
    const attack = preview?.attack_active
    const what =
      scope == null
        ? 'Перебудувати ВСІ треки зі збережених повідомлень?'
        : `Перебудувати треки за останні ${preview?.scope_messages ?? scope} повідомлень? Старіші лишаться як є.`
    const warn = attack
      ? 'УВАГА: зараз активна атака — перебудова може порушити живий трекінг. Продовжити попри це?'
      : `${what} Поточні треки/інциденти в цьому проміжку буде замінено (raw-повідомлення збережуться). ~5% треків, яким потрібен LLM, не відновляться.`
    if (!window.confirm(warn)) return
    setRunning(true)
    setError(null)
    try {
      setResult(await applyReprocess(attack ?? false, true, scope ?? undefined))
      loadPreview()
    } catch {
      setError('Перебудова не вдалася')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-4">
      <p className="text-xs text-slate-500">
        Прогонить усі збережені повідомлення через поточний парсер і перебудовує треки — щоб
        застосувати свіжі виправлення парсера до історії, без зміни змінних середовища та
        перезапуску.
      </p>

      {preview && (
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-slate-300">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span>Повідомлень: <b className="font-mono">{preview.raw_messages}</b></span>
            <span>Треків: <b className="font-mono">{preview.current.tracks}</b></span>
            <span>Подій: <b className="font-mono">{preview.current.events}</b></span>
            <span>Атак: <b className="font-mono">{preview.current.incidents}</b></span>
          </div>
        </div>
      )}

      <ReprocessScope last={last} onChange={setLast} preview={preview} />

      {preview?.attack_active && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          <AlertTriangle size={14} className="shrink-0" />
          Зараз активна атака — перебудову краще відкласти.
        </div>
      )}

      <button
        onClick={run}
        disabled={running || !preview}
        className="self-start rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-300 hover:bg-rose-500/20 disabled:opacity-40"
      >
        {running ? 'Перебудова…' : 'Перебудувати треки'}
      </button>

      {error && <p className="text-xs text-rose-400">{error}</p>}
      {result && <ReprocessDiff result={result} />}
    </div>
  )
}
