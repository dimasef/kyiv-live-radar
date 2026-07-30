import { ChevronLeft, Info } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchUserCollection, type Collection } from '@/api'
import { CARDS, collectionCounts, type CardDef } from '@/lib/cards'
import { collectionUserId, useRoute } from '@/router'
import { useRadar } from '@/store'

import CardModal from '../CardModal'
import CardGrid from './CardGrid'
import RarityTabs, { type Tab } from './RarityTabs'
import RulesModal from './RulesModal'

/** Dedicated «Колекція» page with rarity tabs. Shows your own collection
 * (`/collection`) or a friend's (`/collection/<id>`, server-gated to friends). */
export default function CollectionPage() {
  const route = useRoute()
  const friendId = collectionUserId(route)
  const authed = useRadar((s) => s.authStatus === 'authed')
  const myCollection = useRadar((s) => s.collection)
  const loadCollection = useRadar((s) => s.loadCollection)
  const friends = useRadar((s) => s.friends)

  const [friendCol, setFriendCol] = useState<Collection | null>(null)
  const [denied, setDenied] = useState(false)
  const [tab, setTab] = useState<Tab>('all')
  const [selected, setSelected] = useState<CardDef | null>(null)
  const [showRules, setShowRules] = useState(false)

  // Load the right collection: a friend's over the network, your own from store.
  useEffect(() => {
    if (friendId != null) {
      setFriendCol(null)
      setDenied(false)
      fetchUserCollection(friendId)
        .then(setFriendCol)
        .catch(() => setDenied(true))
    } else if (authed && !myCollection) {
      void loadCollection().catch(() => {})
    }
  }, [friendId, authed, myCollection, loadCollection])

  if (!authed) return <Centered>Ви не увійшли.</Centered>
  if (friendId != null && denied) return <Centered>Колекція доступна лише друзям.</Centered>

  const collection = friendId != null ? friendCol : myCollection
  const counts = collectionCounts(collection?.cards)
  const total = collection?.card_count ?? CARDS.length
  const friend = friendId != null ? friends.find((f) => f.id === friendId) : null
  const ownerName = friend ? friend.display_name || friend.email || 'Друг' : null

  const visible = CARDS.filter((c) => tab === 'all' || c.rarity === tab)

  return (
    <div className="h-full overflow-y-auto bg-ink-950 px-4 py-6 text-slate-200">
      <div className="mx-auto max-w-3xl lg:max-w-5xl">
        <header className="mb-5 flex items-start gap-3">
          <button
            onClick={() => window.history.back()}
            aria-label="Назад"
            className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-slate-100"
          >
            <ChevronLeft size={18} />
          </button>
          <div className="min-w-0 flex-1">
            <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-phosphor-soft">
              Kyiv Live Radar // Колекція
            </span>
            <h1 className="font-display text-xl font-bold text-slate-100">
              {ownerName ? `Картки: ${ownerName}` : 'Мої картки'}
            </h1>
          </div>
          {friendId == null && (
            <button
              onClick={() => setShowRules(true)}
              aria-label="Як отримати картки"
              className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-200"
            >
              <Info size={16} />
            </button>
          )}
        </header>

        <RarityTabs tab={tab} onSelect={setTab} counts={counts} total={total} />
        <CardGrid cards={visible} counts={counts} onSelect={setSelected} />
      </div>

      {selected && (
        <CardModal card={selected} count={counts.get(selected.id) ?? 0} onClose={() => setSelected(null)} />
      )}
      {showRules && <RulesModal onClose={() => setShowRules(false)} />}
    </div>
  )
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center bg-ink-950 text-sm text-slate-400">
      {children}
    </div>
  )
}
