import { useRadar } from "@/store";

import CollectionSummaryCard from "./CollectionSummaryCard";
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

        {(gamification || hasCards) && <CollectionSummaryCard collection={collection} />}

        {/* Contacts */}
        <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4">
          <h2 className="panel-title mb-3">Контакти</h2>
          <ContactsSection />
        </div>
      </div>
    </div>
  );
}
