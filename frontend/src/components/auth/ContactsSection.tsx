import { Check, ChevronRight, UserPlus, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError, type Friend, type FriendUserBrief } from '@/api'
import Avatar from '@/components/common/Avatar'
import Switch from '@/components/common/Switch'
import { contactStyleOf } from '@/lib/contactMarker'
import { useRadar } from '@/store'

import ContactProfileModal from './ContactProfileModal'
import MarkerGlyph from './MarkerGlyph'

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
            <IncomingRow key={r.id} req={r.user} id={r.id} />
          ))}
        </SubList>
      )}
      {requests.outgoing.length > 0 && (
        <SubList label={t('friends.outgoing')}>
          {requests.outgoing.map((r) => (
            <OutgoingRow key={r.id} req={r.user} id={r.id} />
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

/** A titled group of person rows. */
function SubList({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="panel-title mb-1">{label}</p>
      <ul className="-mx-1.5 space-y-0.5">{children}</ul>
    </div>
  )
}

function personLabel(u: { display_name: string | null; email: string | null }): string {
  return u.display_name || u.email || '—'
}

/** Shared layout for a request row: avatar + name on the left, actions right. */
function PersonRow({ user, children }: { user: FriendUserBrief; children: ReactNode }) {
  return (
    <li className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[13px] text-slate-300">
      <Avatar name={personLabel(user)} avatarUrl={user.avatar_url} size={28} />
      <span className="min-w-0 flex-1 truncate">{personLabel(user)}</span>
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

function IncomingRow({ req, id }: { req: FriendUserBrief; id: number }) {
  const { t } = useTranslation()
  const accept = useRadar((s) => s.acceptRequest)
  const decline = useRadar((s) => s.declineRequest)
  return (
    <PersonRow user={req}>
      <IconBtn
        onClick={() => void accept(id).catch(() => {})}
        label={t('friends.accept')}
        className="text-emerald-400 hover:bg-emerald-400/10"
      >
        <Check size={15} />
      </IconBtn>
      <IconBtn
        onClick={() => void decline(id).catch(() => {})}
        label={t('friends.decline')}
        className="text-red-400 hover:bg-red-400/10"
      >
        <X size={15} />
      </IconBtn>
    </PersonRow>
  )
}

function OutgoingRow({ req, id }: { req: FriendUserBrief; id: number }) {
  const { t } = useTranslation()
  const decline = useRadar((s) => s.declineRequest)
  return (
    <PersonRow user={req}>
      <span className="text-[10px] uppercase tracking-wide text-slate-600">
        {t('friends.pending')}
      </span>
      <IconBtn
        onClick={() => void decline(id).catch(() => {})}
        label={t('friends.cancel')}
        className="text-slate-500 hover:bg-white/5 hover:text-slate-300"
      >
        <X size={15} />
      </IconBtn>
    </PersonRow>
  )
}

/** An accepted contact — the whole row opens their profile (avatar, home
 * controls, remove). The marker glyph on the right previews how they show on the
 * map (dimmed when hidden). */
function FriendRow({ friend }: { friend: Friend }) {
  const { t } = useTranslation()
  const style = contactStyleOf(useRadar((s) => s.contactStyles[friend.id]))
  const hidden = useRadar((s) => s.hiddenHomeIds.includes(friend.id))
  const [open, setOpen] = useState(false)

  return (
    <li>
      <button
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] text-slate-300 hover:bg-white/[0.03]"
      >
        <Avatar name={personLabel(friend)} avatarUrl={friend.avatar_url} size={28} />
        <span className="min-w-0 flex-1 truncate">{personLabel(friend)}</span>
        {friend.home ? (
          <span className={hidden ? 'opacity-40' : ''}>
            <MarkerGlyph icon={style.icon} color={style.color} />
          </span>
        ) : (
          <span className="text-[10px] text-slate-600">{t('friends.notSharing')}</span>
        )}
        <ChevronRight size={15} className="flex-none text-slate-600" />
      </button>
      {open && <ContactProfileModal contact={friend} onClose={() => setOpen(false)} />}
    </li>
  )
}
