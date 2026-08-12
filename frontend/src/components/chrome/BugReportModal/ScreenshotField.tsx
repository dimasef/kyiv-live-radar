import { ImagePlus, X } from 'lucide-react'
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'

/** Pick one screenshot, or look at the one already picked. Purely the surface:
 * turning a file into a stored image happens in the form (one place, shared
 * with pasting into the textarea). */
export default function ScreenshotField({
  value,
  onFile,
  onClear,
}: {
  value: string | null
  onFile: (file: File) => void
  onClear: () => void
}) {
  const { t } = useTranslation()
  const input = useRef<HTMLInputElement>(null)

  if (value) {
    return (
      <div className="relative mt-2 overflow-hidden rounded-lg border border-white/10">
        <img src={value} alt="" className="max-h-56 w-full bg-black/40 object-contain" />
        <button
          type="button"
          onClick={onClear}
          aria-label={t('bug.remove')}
          className="absolute right-1.5 top-1.5 rounded-full bg-black/70 p-1 text-slate-300 hover:text-slate-100"
        >
          <X size={14} />
        </button>
      </div>
    )
  }

  return (
    <>
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-white/15 px-3 py-3 text-xs text-slate-400 transition-colors hover:border-white/30 hover:text-slate-200"
      >
        <ImagePlus size={15} />
        {t('bug.addScreenshot')}
      </button>
      <p className="mt-1 text-[11px] text-slate-600">{t('bug.pasteHint')}</p>
      <input
        ref={input}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFile(file)
          e.target.value = ''
        }}
      />
    </>
  )
}
