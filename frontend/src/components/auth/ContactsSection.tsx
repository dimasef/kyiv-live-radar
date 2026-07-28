import { Check, Eye, EyeOff, Trash2, UserPlus, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError, type Friend, type FriendRequest } from '@/api'
import ConfirmModal from '@/components/common/ConfirmModal'
import {
  CONTACT_COLORS,
  CONTACT_ICONS,
  contactMarkerSvg,
  contactStyleOf,
  type ContactStyle,
} from '@/lib/contactMarker'
import { useRadar } from '@/store'

/** Contacts + shareable home — the profile page's "Контакти" section body.
 * AccountPage already gates on auth and supplies the section heading, so this
 * renders just the controls. */
export default function ContactsSection() {
  const { t } = useTranslation()
  const home = useRadar((s) => s.home)
  const friends = useRadar((s) => s.friends)
  const requests = useRadar((s) => s.friendRequests)
  const shareHome = useRadar((s) => s.shareHome)
  const requestFriend = useRadar((s) => s.requestFriend)
  const setShareHome = useRadar((s) => s.setShareHome)

  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const value = email.trim()
    if (!value || busy) return
    setBusy(true)
    setMsg(null)
    try {
      const { status } = await requestFriend(value)
      setEmail('')
      setMsg({ tone: 'ok', text: t(`friends.result.${status}`) })
    } catch (e) {
      const key = e instanceof ApiError && e.status === 404 ? 'notFound' : 'failed'
      setMsg({ tone: 'err', text: t(`friends.error.${key}`) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Share-my-home switch (privacy gate) — a home must be set to be useful. */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] text-slate-200">{t('friends.shareHomeLabel')}</p>
          <p className="text-[11px] leading-snug text-slate-500">
            {home ? t('friends.shareHomeHint') : t('friends.needHome')}
          </p>
        </div>
        <Switch
          checked={shareHome}
          disabled={!home}
          label={t('friends.shareHomeLabel')}
          onChange={() => void setShareHome(!shareHome).catch(() => {})}
        />
      </div>

      {/* Add a contact by email. */}
      <div>
        <div className="flex gap-2">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void submit()}
            placeholder={t('friends.emailPlaceholder')}
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] text-slate-200 placeholder:text-slate-600 focus:border-phosphor/40 focus:outline-none"
          />
          <button
            onClick={() => void submit()}
            disabled={busy || !email.trim()}
            className="btn btn--accent flex items-center gap-1.5 disabled:opacity-40"
          >
            <UserPlus size={14} />
            {t('friends.add')}
          </button>
        </div>
        {msg && (
          <p className={`mt-1.5 text-xs ${msg.tone === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>
            {msg.text}
          </p>
        )}
      </div>

      {requests.incoming.length > 0 && (
        <SubList label={t('friends.incoming')}>
          {requests.incoming.map((r) => (
            <IncomingRow key={r.id} req={r} />
          ))}
        </SubList>
      )}
      {requests.outgoing.length > 0 && (
        <SubList label={t('friends.outgoing')}>
          {requests.outgoing.map((r) => (
            <OutgoingRow key={r.id} req={r} />
          ))}
        </SubList>
      )}

      <SubList label={t('friends.list')}>
        {friends.length === 0 ? (
          <li className="px-1.5 py-1 text-xs text-slate-600">{t('friends.empty')}</li>
        ) : (
          friends.map((f) => <FriendRow key={f.id} friend={f} />)
        )}
      </SubList>
    </div>
  )
}

function Switch({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean
  disabled?: boolean
  label: string
  onChange: () => void
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={`inline-flex h-5 w-9 flex-none items-center rounded-full transition-colors duration-200 disabled:opacity-40 ${
        checked ? 'bg-phosphor/70' : 'bg-white/15'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
          checked ? 'translate-x-4' : 'translate-x-1'
        }`}
      />
    </button>
  )
}

/** A titled group of person rows. */
function SubList({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="panel-title mb-1">{label}</p>
      <ul className="-mx-1.5">{children}</ul>
    </div>
  )
}

function personLabel(u: { display_name: string | null; email: string | null }): string {
  return u.display_name || u.email || '—'
}

/** Shared layout for every person row: name on the left, actions on the right. */
function Row({ name, children }: { name: string; children: ReactNode }) {
  return (
    <li className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[13px] text-slate-300 hover:bg-white/[0.03]">
      <span className="min-w-0 flex-1 truncate">{name}</span>
      {children}
    </li>
  )
}

function IconBtn({
  onClick,
  label,
  className,
  children,
}: {
  onClick: () => void
  label: string
  className: string
  children: ReactNode
}) {
  return (
    <button onClick={onClick} aria-label={label} className={`flex-none rounded p-1 ${className}`}>
      {children}
    </button>
  )
}

function IncomingRow({ req }: { req: FriendRequest }) {
  const { t } = useTranslation()
  const accept = useRadar((s) => s.acceptRequest)
  const decline = useRadar((s) => s.declineRequest)
  return (
    <Row name={personLabel(req.user)}>
      <IconBtn
        onClick={() => void accept(req.id).catch(() => {})}
        label={t('friends.accept')}
        className="text-emerald-400 hover:bg-emerald-400/10"
      >
        <Check size={15} />
      </IconBtn>
      <IconBtn
        onClick={() => void decline(req.id).catch(() => {})}
        label={t('friends.decline')}
        className="text-red-400 hover:bg-red-400/10"
      >
        <X size={15} />
      </IconBtn>
    </Row>
  )
}

function OutgoingRow({ req }: { req: FriendRequest }) {
  const { t } = useTranslation()
  const decline = useRadar((s) => s.declineRequest)
  return (
    <Row name={personLabel(req.user)}>
      <span className="text-[10px] uppercase tracking-wide text-slate-600">
        {t('friends.pending')}
      </span>
      <IconBtn
        onClick={() => void decline(req.id).catch(() => {})}
        label={t('friends.cancel')}
        className="text-slate-500 hover:bg-white/5 hover:text-slate-300"
      >
        <X size={15} />
      </IconBtn>
    </Row>
  )
}

/** A small inline SVG of a marker, for the swatch button and picker options. */
function MarkerGlyph({ icon, color, size = 15 }: { icon: string; color: string; size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-flex flex-none"
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: contactMarkerSvg(icon, color, size) }}
    />
  )
}

/** Colour + icon grid for one contact's map marker. */
function StylePicker({
  style,
  onChange,
}: {
  style: ContactStyle
  onChange: (s: ContactStyle) => void
}) {
  return (
    <div className="mt-1.5 space-y-2 rounded-lg border border-white/10 bg-white/[0.02] p-2">
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

function FriendRow({ friend }: { friend: Friend }) {
  const { t } = useTranslation()
  const unfriend = useRadar((s) => s.unfriend)
  const toggleHome = useRadar((s) => s.toggleContactHome)
  const hidden = useRadar((s) => s.hiddenHomeIds.includes(friend.id))
  const style = contactStyleOf(useRadar((s) => s.contactStyles[friend.id]))
  const setStyle = useRadar((s) => s.setContactStyle)
  const [asking, setAsking] = useState(false)
  const [editing, setEditing] = useState(false)
  const sharesHome = friend.home != null

  return (
    <li className="rounded-md px-1.5 py-1 hover:bg-white/[0.03]">
      <div className="flex items-center gap-2 text-[13px] text-slate-300">
        <span className="min-w-0 flex-1 truncate">{personLabel(friend)}</span>
        {sharesHome ? (
          <>
            {/* Pick this contact's marker colour + icon on the user's own map. */}
            <button
              onClick={() => setEditing((v) => !v)}
              aria-label={t('friends.markerStyle')}
              className={`flex-none rounded p-1 hover:bg-white/5 ${editing ? 'bg-white/10' : ''}`}
            >
              <MarkerGlyph icon={style.icon} color={style.color} />
            </button>
            <IconBtn
              onClick={() => toggleHome(friend.id)}
              label={hidden ? t('friends.showOnMap') : t('friends.hideFromMap')}
              className={hidden ? 'text-slate-600 hover:text-slate-300' : 'hover:bg-white/5'}
            >
              {hidden ? <EyeOff size={14} /> : <Eye size={14} style={{ color: style.color }} />}
            </IconBtn>
          </>
        ) : (
          <span className="text-[10px] text-slate-600">{t('friends.notSharing')}</span>
        )}
        <IconBtn
          onClick={() => setAsking(true)}
          label={t('friends.remove')}
          className="text-slate-500 hover:bg-red-400/10 hover:text-red-400"
        >
          <Trash2 size={14} />
        </IconBtn>
      </div>

      {editing && sharesHome && (
        <StylePicker style={style} onChange={(s) => setStyle(friend.id, s)} />
      )}

      {asking && (
        <ConfirmModal
          message={t('friends.removeConfirm', { name: personLabel(friend) })}
          confirmLabel={t('friends.remove')}
          cancelLabel={t('friends.cancel')}
          tone="danger"
          onConfirm={() => void unfriend(friend.id).catch(() => {})}
          onCancel={() => setAsking(false)}
        />
      )}
    </li>
  )
}
