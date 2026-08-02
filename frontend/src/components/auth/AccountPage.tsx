import { ChevronRight } from "lucide-react";

import type { Collection } from "@/api";
import { CARDS, RARITIES, RARITY_STYLE, collectionCounts, rarityBreakdown } from "@/lib/cards";
import { COLLECTION_PATH, navigate } from "@/router";
import { useRadar } from "@/store";

import ContactsSection from "./ContactsSection";
import IdentityCard from "./IdentityCard";

/** Signed-in user's account page: an identity card, a collection summary and the
 * contact list — each in a consistent bordered card. Quick navigation and
 * sign-out live in the navbar avatar menu, so they aren't duplicated here. */
export default function AccountPage() {
  const user = useRadar((s) => s.user);
  const status = useRadar((s) => s.authStatus);
  const gamification = useRadar((s) => s.gamification);
  const collection = useRadar((s) => s.collection);
  const hasCards = (collection?.total_analyses ?? 0) > 0;

  if (status !== "authed" || !user) {
    return (
      <div className="flex h-full items-center justify-center bg-ink-950 text-sm text-slate-400">
        {status === "unknown" ? "Завантаження…" : "Ви не увійшли."}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-ink-950 px-4 py-8 text-slate-200">
      <div className="mx-auto max-w-md space-y-4 lg:max-w-2xl">
        <IdentityCard user={user} />

        {(gamification || hasCards) && <CollectionCard collection={collection} />}

        {/* Contacts */}
        <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4">
          <h2 className="panel-title mb-3">Контакти</h2>
          <ContactsSection />
        </div>
      </div>
    </div>
  );
}

/** Collection summary: overall progress + a per-rarity breakdown, the whole card
 * links to the full collection page. */
function CollectionCard({ collection }: { collection: Collection | null }) {
  const counts = collectionCounts(collection?.cards);
  const breakdown = rarityBreakdown(counts);
  const total = collection?.card_count ?? CARDS.length;
  const pct = total ? Math.round((counts.size / total) * 100) : 0;

  return (
    <button
      onClick={() => navigate(COLLECTION_PATH)}
      className="w-full rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4 text-left transition-colors hover:border-phosphor/30"
    >
      <div className="flex items-center justify-between">
        <span className="panel-title">Колекція карток</span>
        <ChevronRight size={16} className="text-slate-500" />
      </div>
      <p className="mt-2 font-mono text-xs text-slate-500">
        Зібрано <span className="text-phosphor-soft">{counts.size}</span> / {total}
      </p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="h-full rounded-full bg-phosphor/70" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {RARITIES.map((r) => (
          <span key={r} className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <i className="h-[6px] w-[6px] rounded-full" style={{ background: RARITY_STYLE[r].rc }} />
            {RARITY_STYLE[r].label}
            <span className="font-mono text-slate-500">
              {breakdown[r].have}/{breakdown[r].total}
            </span>
          </span>
        ))}
      </div>
    </button>
  );
}
