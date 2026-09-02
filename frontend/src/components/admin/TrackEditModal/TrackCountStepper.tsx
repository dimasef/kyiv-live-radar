import { useState } from 'react'

import { setThreatCount } from '@/api'
import type { Threat } from '@/types'

const MAX = 999

const STEP =
  'inline-flex h-9 w-9 flex-none items-center justify-center text-base leading-none ' +
  'text-slate-300 transition-colors hover:bg-white/[0.07] active:bg-white/10 ' +
  'disabled:opacity-30 disabled:hover:bg-transparent'

/** How many targets fly under one track — «2х шахеди» is one track carrying
 * two, not two tracks.
 *
 * A ± stepper rather than a text field: every real correction is off by one or
 * two, no phone keyboard has to open, and each tap is a single PATCH exactly
 * like the type select next to it. The «Цілей» label is not decoration — a bare
 * `− 1 +` between a type select and a red button read as a page counter.
 *
 * Setting it by hand LATCHES the number (the pipeline otherwise grows it as a
 * running max and would undo a correction downwards on the next message that
 * restated a bigger group), so a latched count says so and offers «авто» back. */
export default function TrackCountStepper({
  track,
  onChanged,
}: {
  track: Threat
  onChanged: (track: Threat) => void
}) {
  const [pending, setPending] = useState(false)

  const send = (count: number | null) => {
    setPending(true)
    setThreatCount(track.id, count)
      .then(onChanged)
      .catch(() => {})
      .finally(() => setPending(false))
  }

  return (
    <span className="inline-flex flex-none items-center gap-1.5">
      <span className="text-[11px] text-slate-500">Цілей</span>
      <span className="inline-flex items-center overflow-hidden rounded-lg border border-white/15 bg-ink-900">
        <button
          onClick={() => send(track.target_count - 1)}
          disabled={pending || track.target_count <= 1}
          className={STEP}
          aria-label="Менше цілей"
        >
          −
        </button>
        <span
          className="min-w-7 text-center font-mono text-sm tabular-nums text-slate-100"
          aria-live="polite"
        >
          {track.target_count}
        </span>
        <button
          onClick={() => send(track.target_count + 1)}
          disabled={pending || track.target_count >= MAX}
          className={STEP}
          aria-label="Більше цілей"
        >
          +
        </button>
      </span>
      {track.target_count_locked && (
        <button
          onClick={() => send(null)}
          disabled={pending}
          title="Кількість виставлено вручну — повернути ту, яку виводить парсер"
          className="inline-flex h-9 flex-none items-center rounded-lg px-1.5 text-[10px] text-amber-300/80 transition-colors hover:bg-amber-500/10 hover:text-amber-200"
        >
          вручну ✕
        </button>
      )}
    </span>
  )
}
