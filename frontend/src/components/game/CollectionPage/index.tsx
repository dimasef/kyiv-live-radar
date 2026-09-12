import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchUserCollection, type Collection } from '@/api'
import CardModal from '@/components/game/CardModal'
import { CARDS, RARITIES, collectionCounts, type CardDef } from '@/lib/cards'
import { collectionUserId, useRoute } from '@/router'
import { useRadar } from '@/store'

import CollectionHeader from './CollectionHeader'
import RaritySection from './RaritySection'
import RulesModal from './RulesModal'
import { SECTION_IDS, rarityOfSection, sectionId } from './sections'
import { useNewCards } from './useNewCards'
import { useSectionNav } from './useSectionNav'

/** Dedicated «Колекція» page: one section per rarity, the rarity rail in the
 * sticky bar navigating between them. Shows your own collection
 * (`/collection`) or a friend's (`/collection/<id>`, server-gated to friends). */
export default function CollectionPage() {
  const route = useRoute()
  const friendId = collectionUserId(route)
  const authed = useRadar((s) => s.authStatus === 'authed')
  const myCollection = useRadar((s) => s.collection)
  const loadCollection = useRadar((s) => s.loadCollection)
  const friends = useRadar((s) => s.friends)
  const myUserId = useRadar((s) => s.user?.id ?? null)

  const [friendCol, setFriendCol] = useState<Collection | null>(null)
  const [denied, setDenied] = useState(false)
  const [selected, setSelected] = useState<CardDef | null>(null)
  const [showRules, setShowRules] = useState(false)
  const sticky = useRef<HTMLDivElement>(null)
  const { active, jumpTo, scrollerRef } = useSectionNav(sticky, SECTION_IDS)

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

  // Only your own freshly-obtained cards shimmer, and only the first time you
  // open the collection after the drop (see useNewCards).
  const isOwn = friendId == null
  const ownedIds = isOwn ? (myCollection?.cards.map((c) => c.card_id) ?? []) : []
  const newIds = useNewCards(myUserId, ownedIds, isOwn && myCollection != null)

  if (!authed) return <Centered>Ви не увійшли.</Centered>
  if (friendId != null && denied) return <Centered>Колекція доступна лише друзям.</Centered>

  const collection = friendId != null ? friendCol : myCollection
  const counts = collectionCounts(collection?.cards)
  const total = collection?.card_count ?? CARDS.length
  const friend = friendId != null ? friends.find((f) => f.id === friendId) : null
  const ownerName = friend ? friend.display_name || friend.email || 'Друг' : null

  return (
    <div ref={scrollerRef} className="h-full overflow-y-auto bg-ink-950 px-4 pb-6 text-slate-200">
      <div className="mx-auto max-w-3xl lg:max-w-5xl">
        <CollectionHeader
          stickyRef={sticky}
          ownerName={ownerName}
          onShowRules={isOwn ? () => setShowRules(true) : undefined}
          active={rarityOfSection(active)}
          onJump={(r) => jumpTo(sectionId(r))}
          counts={counts}
          total={total}
        />

        {RARITIES.map((r) => (
          <RaritySection
            key={r}
            rarity={r}
            cards={CARDS.filter((c) => c.rarity === r)}
            counts={counts}
            newIds={newIds}
            onSelect={setSelected}
          />
        ))}
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
