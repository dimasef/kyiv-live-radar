import { ArrowRight, Camera, Trash2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import Avatar from '@/components/common/Avatar'
import ConfirmModal from '@/components/common/ConfirmModal'
import { decodeImage } from '@/lib/avatarImage'
import { useRadar } from '@/store'

import AvatarEditor from './AvatarEditor'

// Hidden but reachable: `group-focus-within` means tabbing to the camera brings
// the overlay with it, and the hover half is gated on the pointer actually
// supporting hover so a phone never leaves the controls stuck invisible.
const REVEALED_ON_HOVER_OR_FOCUS =
  'pointer-events-none opacity-0 ' +
  'group-focus-within:pointer-events-auto group-focus-within:opacity-100 ' +
  '[@media(hover:hover)]:group-hover:pointer-events-auto ' +
  '[@media(hover:hover)]:group-hover:opacity-100'

/** The account avatar, with a camera and a bin laid over it.
 *
 * Two ways in, because one alone fails somebody. Hovering the picture reveals
 * them on a desktop, which is the quick path — but hover doesn't exist on a
 * phone, so edit mode (the card's pencil) pins them open for everyone else.
 * Keyboard focus reveals them too, so they're never focusable while invisible.
 *
 * The picture itself is stored inline on the account (backend
 * app/auth/avatar.py), so it follows the user to every device like the rest of
 * their profile. */
export default function AvatarPicker({
  name,
  editing,
  size = 80,
}: {
  name: string
  editing: boolean
  size?: number
}) {
  const { t } = useTranslation()
  const user = useRadar((s) => s.user)
  const updateProfile = useRadar((s) => s.updateProfile)
  const fileRef = useRef<HTMLInputElement>(null)
  const [bitmap, setBitmap] = useState<ImageBitmap | null>(null)
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pick = async (file: File | undefined) => {
    if (!file) return
    setError(null)
    try {
      setBitmap(await decodeImage(file))
    } catch {
      setError(t('avatar.unreadable'))
    }
  }

  const save = async (dataUrl: string) => {
    setSaving(true)
    try {
      await updateProfile({ avatar_url: dataUrl })
      setBitmap(null)
    } catch {
      setError(t('avatar.failed'))
    } finally {
      setSaving(false)
    }
  }

  const closeEditor = () => {
    // Bitmaps hold decoded pixels — a few MB for a phone photo. Releasing them
    // matters here because picking three photos in a row would otherwise keep
    // all three alive until GC felt like it.
    bitmap?.close()
    setBitmap(null)
  }

  const iconBtn =
    'flex items-center justify-center rounded-full bg-ink-950/70 text-slate-200 ring-1 ring-white/15 transition-colors duration-200'
  const iconSize = Math.round(size * 0.22)
  const iconBox = { width: iconSize * 1.7, height: iconSize * 1.7 }

  return (
    <div className="flex-none">
      <div className="group relative" style={{ width: size, height: size }}>
        <Avatar name={name} avatarUrl={user?.avatar_url} size={size} />
        <div
          className={`absolute inset-0 flex items-center justify-center gap-1.5 rounded-full bg-ink-950/55 transition-opacity duration-200 ${
            editing ? 'opacity-100' : REVEALED_ON_HOVER_OR_FOCUS
          }`}
        >
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className={`${iconBtn} hover:text-phosphor-soft`}
            style={iconBox}
            aria-label={t('avatar.change')}
            title={t('avatar.change')}
          >
            <Camera size={iconSize} />
          </button>
          {user?.avatar_url && (
            <button
              type="button"
              onClick={() => setConfirmingRemove(true)}
              className={`${iconBtn} hover:text-rose-300`}
              style={iconBox}
              aria-label={t('avatar.remove')}
              title={t('avatar.remove')}
            >
              <Trash2 size={iconSize} />
            </button>
          )}
        </div>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          void pick(e.target.files?.[0])
          // Reset so re-picking the SAME file still fires a change event.
          e.target.value = ''
        }}
      />
      {error && (
        <p className="mt-1 text-[11px] leading-tight text-red-400" style={{ maxWidth: size }}>
          {error}
        </p>
      )}

      {bitmap && (
        <AvatarEditor bitmap={bitmap} saving={saving} onSave={save} onCancel={closeEditor} />
      )}
      {confirmingRemove && (
        <ConfirmModal
          tone="danger"
          confirmLabel={t('avatar.removeConfirmYes')}
          cancelLabel={t('avatar.cancel')}
          onCancel={() => setConfirmingRemove(false)}
          onConfirm={() => {
            setConfirmingRemove(false)
            void updateProfile({ avatar_url: null }).catch(() => setError(t('avatar.failed')))
          }}
          message={
            <>
              <p>{t('avatar.removeConfirm')}</p>
              {/* Shows the actual before/after rather than describing it — the
                  fallback monogram is a surprise otherwise. */}
              <div className="mt-4 flex items-center justify-center gap-4">
                <Avatar name={name} avatarUrl={user?.avatar_url} size={56} />
                <ArrowRight size={16} className="flex-none text-slate-500" />
                <Avatar name={name} size={56} />
              </div>
            </>
          }
        />
      )}
    </div>
  )
}
