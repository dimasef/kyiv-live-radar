import { Layers, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import type { Friend } from '@/api'
import Avatar from '@/components/common/Avatar'
import ConfirmModal from '@/components/common/ConfirmModal'
import Switch from '@/components/common/Switch'
import {
  CONTACT_COLORS,
  CONTACT_ICONS,
  contactStyleOf,
  type ContactStyle,
} from '@/lib/contactMarker'
import { useDismissTransition } from '@/lib/useDismissTransition'
import { collectionPath, navigate } from '@/router'
import { useRadar } from '@/store'

import MarkerGlyph from './MarkerGlyph'

function personLabel(u: { display_name: string | null; email: string | null }): string {
  return u.display_name || u.email || '—'
}

/** A contact's profile: avatar + identity, and — for a contact who shares a home
 * — the per-contact map controls (show/hide on my map, marker colour + icon) and
 * removal. All data comes from the store's `friends` entry; no server fetch. */
export default function ContactProfileModal({
  contact,
  onClose,
}: {
  contact: Friend
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { shown, close } = useDismissTransition(onClose)
  const unfriend = useRadar((s) => s.unfriend)
  const toggleHome = useRadar((s) => s.toggleContactHome)
  const setStyle = useRadar((s) => s.setContactStyle)
  const hidden = useRadar((s) => s.hiddenHomeIds.includes(contact.id))
  const gamification = useRadar((s) => s.gamification)
  const style = contactStyleOf(useRadar((s) => s.contactStyles[contact.id]))
  const [asking, setAsking] = useState(false)
  const sharesHome = contact.home != null

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
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Avatar name={personLabel(contact)} avatarUrl={contact.avatar_url} size={48} />
            <div className="min-w-0">
              <p className="truncate font-display text-base font-bold text-slate-100">
                {personLabel(contact)}
              </p>
              {contact.email && <p className="truncate text-xs text-slate-500">{contact.email}</p>}
            </div>
          </div>
          <button
            onClick={close}
            aria-label={t('panel.close')}
            className="flex-none text-slate-400 transition-colors hover:text-slate-100"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-5">
          <p className="panel-title mb-2">{t('friends.homeOnMap')}</p>
          {sharesHome ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 text-[13px] text-slate-300">
                  <span className={hidden ? 'opacity-40' : ''}>
                    <MarkerGlyph icon={style.icon} color={style.color} size={18} />
                  </span>
                  {hidden ? t('friends.hiddenOnMap') : t('friends.shownOnMap')}
                </span>
                <Switch
                  checked={!hidden}
                  label={hidden ? t('friends.showOnMap') : t('friends.hideFromMap')}
                  onChange={() => toggleHome(contact.id)}
                />
              </div>
              {!hidden && <StylePicker style={style} onChange={(s) => setStyle(contact.id, s)} />}
            </>
          ) : (
            <p className="text-[13px] text-slate-500">{t('friends.notSharing')}</p>
          )}
        </div>

        {gamification && (
          <button
            onClick={() => {
              navigate(collectionPath(contact.id))
              close()
            }}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-phosphor/25 bg-phosphor/[0.06] px-4 py-2 text-sm text-phosphor-soft transition-colors hover:border-phosphor/40"
          >
            <Layers size={15} /> Колекція карток
          </button>
        )}

        <button
          onClick={() => setAsking(true)}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-red-400/25 bg-red-400/[0.05] px-4 py-2 text-sm text-red-300 transition-colors hover:border-red-400/40"
        >
          <Trash2 size={15} /> {t('friends.remove')}
        </button>
      </div>

      {asking && (
        <ConfirmModal
          message={t('friends.removeConfirm', { name: personLabel(contact) })}
          confirmLabel={t('friends.remove')}
          cancelLabel={t('friends.cancel')}
          tone="danger"
          onConfirm={() => void unfriend(contact.id).catch(() => {})}
          onCancel={() => setAsking(false)}
        />
      )}
    </div>,
    document.body,
  )
}

/** Colour + icon grid for this contact's map marker. */
function StylePicker({
  style,
  onChange,
}: {
  style: ContactStyle
  onChange: (s: ContactStyle) => void
}) {
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-white/10 bg-white/[0.02] p-2">
      <div className="flex flex-wrap gap-1.5">
        {CONTACT_COLORS.map((c) => (
          <button
            key={c}
            onClick={() => onChange({ ...style, color: c })}
            aria-label={c}
            className={`h-5 w-5 rounded-full transition ${
              c === style.color ? 'ring-2 ring-white/80' : 'ring-1 ring-white/10'
            }`}
            style={{ background: c }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        {CONTACT_ICONS.map((ic) => (
          <button
            key={ic}
            onClick={() => onChange({ ...style, icon: ic })}
            aria-label={ic}
            className={`rounded p-1 transition ${
              ic === style.icon ? 'bg-white/10 ring-1 ring-white/40' : 'hover:bg-white/5'
            }`}
          >
            <MarkerGlyph icon={ic} color={style.color} size={16} />
          </button>
        ))}
      </div>
    </div>
  )
}
