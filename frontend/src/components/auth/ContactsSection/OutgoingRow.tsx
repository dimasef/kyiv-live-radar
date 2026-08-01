import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { FriendUserBrief } from '@/api'
import { useRadar } from '@/store'

import PersonRow, { IconBtn } from './PersonRow'

export default function OutgoingRow({ req, id }: { req: FriendUserBrief; id: number }) {
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
