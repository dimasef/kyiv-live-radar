import { Check, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { FriendUserBrief } from '@/api'
import { useRadar } from '@/store'

import PersonRow, { IconBtn } from './PersonRow'

export default function IncomingRow({ req, id }: { req: FriendUserBrief; id: number }) {
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
