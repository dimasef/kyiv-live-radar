import { Loader2 } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import {
  clampFraming,
  drawFramed,
  toAvatarDataUrl,
  DEFAULT_FRAMING,
  PREVIEW_PX,
  type Framing,
} from '@/lib/avatarImage'
import { useDismissTransition } from '@/lib/useDismissTransition'

// Kept in step with clampFraming's bounds in lib/avatarImage.ts.
const ZOOM_MIN = 1
const ZOOM_MAX = 4

/** Position the picked photo inside the square that will be stored.
 *
 * A centre crop alone isn't enough in practice: portrait photos put the face in
 * the upper third, so an automatic square cuts foreheads off. Drag to move,
 * slider to zoom — the preview IS the result (same draw function, different
 * scale), so there's nothing to be surprised by after saving. */
export default function AvatarEditor({
  bitmap,
  saving,
  onSave,
  onCancel,
}: {
  bitmap: ImageBitmap
  saving: boolean
  onSave: (dataUrl: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const { shown, close } = useDismissTransition(onCancel)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [framing, setFraming] = useState<Framing>(DEFAULT_FRAMING)
  const drag = useRef<{ x: number; y: number; from: Framing } | null>(null)

  // Canvas painting is DOM work that has to follow state — exactly what an
  // effect is for (there is no declarative way to express "these pixels").
  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d')
    if (ctx) drawFramed(ctx, bitmap, framing, PREVIEW_PX)
  }, [bitmap, framing])

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, y: e.clientY, from: framing }
  }
  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const start = drag.current
    if (!start) return
    setFraming(
      clampFraming(bitmap, {
        ...start.from,
        offsetX: start.from.offsetX + (e.clientX - start.x),
        offsetY: start.from.offsetY + (e.clientY - start.y),
      }),
    )
  }
  const endDrag = () => {
    drag.current = null
  }

  return createPortal(
    <div
      className={`fixed inset-0 z-[2000] flex items-center justify-center bg-ink-950/80 p-4 backdrop-blur-sm transition-opacity duration-200 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
      onClick={close}
    >
      <div
        className={`w-full max-w-xs rounded-2xl border border-white/10 bg-ink-900 p-5 shadow-2xl transition-all duration-200 ease-out ${
          shown ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-2 scale-95 opacity-0'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="panel-title mb-3">{t('avatar.title')}</p>
        <canvas
          ref={canvasRef}
          width={PREVIEW_PX}
          height={PREVIEW_PX}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          className="mx-auto block w-full max-w-[240px] cursor-grab touch-none rounded-full bg-ink-950 ring-1 ring-white/10 active:cursor-grabbing"
        />
        <label className="mt-4 block text-[11px] text-slate-500">{t('avatar.zoom')}</label>
        <input
          type="range"
          min={ZOOM_MIN}
          max={ZOOM_MAX}
          step={0.05}
          value={framing.zoom}
          onChange={(e) =>
            setFraming((f) => clampFraming(bitmap, { ...f, zoom: Number(e.target.value) }))
          }
          className="range-glow mt-1.5"
          // .range-glow paints its filled portion from --fill; without it the
          // track sits at the 30% default and stops following the thumb.
          style={
            {
              '--fill': `${((framing.zoom - ZOOM_MIN) / (ZOOM_MAX - ZOOM_MIN)) * 100}%`,
            } as CSSProperties
          }
        />
        <p className="mt-3 text-[11px] leading-snug text-slate-500">{t('avatar.hint')}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={close}
            disabled={saving}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-sm font-medium text-slate-300 hover:bg-white/[0.06]"
          >
            {t('avatar.cancel')}
          </button>
          <button
            onClick={() => onSave(toAvatarDataUrl(bitmap, framing))}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-phosphor/20 px-3 py-1.5 text-sm font-semibold text-phosphor-soft hover:bg-phosphor/30"
          >
            {saving && <Loader2 size={13} className="animate-spin" />}
            {t('avatar.save')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
