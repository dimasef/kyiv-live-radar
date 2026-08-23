import { useEffect, useMemo, useRef, useState } from "react";

import { fetchRawSources } from "@/api";
import AdminGate from "@/components/admin/AdminGate";
import { observeVisible } from "@/lib/observers";
import { STORAGE_KEYS, safeGet, safeSet } from "@/lib/storage";
import type { RawOutcomeFilter, RawSource } from "@/types";

import ControlsToggle from "./ControlsToggle";
import LlmStatsStrip from "./LlmStatsStrip";
import RawFilterBar from "./RawFilterBar";
import RawMessageRow from "./RawMessageRow";
import RawToolbar from "./RawToolbar";
import { useRawMessages } from "./useRawMessages";
import { useRawSelection } from "./useRawSelection";

const SEARCH_DEBOUNCE_MS = 300;

/** Admin gate for /raw. The log itself is `RawMessagesView` below. */
export default function RawMessagesPage() {
  return (
    <AdminGate prompt="Увійдіть як адміністратор, щоб переглянути сирі повідомлення.">
      <RawMessagesView />
    </AdminGate>
  );
}

/** The raw-message log itself (every ingested message, including ones the
 * parser suppressed or couldn't localize — distinct from the operator-facing
 * event feed, which only shows messages that became a live sighting). Exported
 * so the admin console can host it as its "Весь Фід" tab; it assumes the caller
 * already gated on admin. */
export function RawMessagesView() {
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState<RawOutcomeFilter | "all">("all");
  const [llm, setLlm] = useState<"all" | "yes" | "no">("all");
  const [sourceId, setSourceId] = useState<number | "all">("all");
  const [sources, setSources] = useState<RawSource[]>([]);
  // Read once at mount rather than through an effect: this is a value that
  // exists before the first render, not something to synchronise afterwards.
  const [controlsOpen, setControlsOpen] = useState(
    () => safeGet(STORAGE_KEYS.rawControlsCollapsed) !== "1",
  );

  const toggleControls = () => {
    const next = !controlsOpen;
    setControlsOpen(next);
    safeSet(STORAGE_KEYS.rawControlsCollapsed, next ? "0" : "1");
  };

  useEffect(() => {
    const t = setTimeout(() => setQ(searchInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    fetchRawSources()
      .then(setSources)
      .catch(() => {});
  }, []);

  const filters = useMemo(
    () => ({ q, outcome, llm, sourceId }),
    [q, outcome, llm, sourceId],
  );
  const {
    items,
    loading,
    done,
    total,
    loadMore,
    apiFilter,
    dropEvent,
    setNotice,
    moveEventToTrack,
    applyTrack,
  } = useRawMessages(filters);
  const selection = useRawSelection({ items, filters, apiFilter, sources });
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    return observeVisible(el, loadMore, { rootMargin: "400px" });
  }, [loadMore]);

  return (
    <div className="flex h-full flex-col bg-ink-950 text-slate-200">
      {/* Fixed header: title, stats, filters and toolbar stay in view while only
          the message list below scrolls — and fold away on demand, because on a
          laptop they ate a third of the viewport of a list read by scrolling. */}
      <div className="shrink-0 border-b border-white/[0.06] px-4 pt-4 pb-3">
        <div className="mx-auto max-w-3xl">
          <ControlsToggle
            open={controlsOpen}
            onToggle={toggleControls}
            loaded={items.length}
            total={total}
            selectedCount={selection.selectedCount}
          />

          {!controlsOpen ? null : (
            <>
              <p className="mt-1 text-xs text-slate-500">
                Усі вхідні повідомлення, включно з тими, що не потрапили у
                Стрічку подій.
              </p>

              <LlmStatsStrip />

              <RawFilterBar
                search={searchInput}
                onSearchChange={setSearchInput}
                outcome={outcome}
                onOutcomeChange={setOutcome}
                llm={llm}
                onLlmChange={setLlm}
                sources={sources}
                sourceId={sourceId}
                onSourceIdChange={setSourceId}
              />

              <RawToolbar
                loaded={items.length}
                total={total}
                selectedCount={selection.selectedCount}
                allLoadedSelected={selection.allLoadedSelected}
                exporting={selection.exporting}
                onExportFiltered={selection.exportFiltered}
                onExportSelected={selection.exportSelected}
                onViewFiltered={selection.viewFiltered}
                onViewSelected={selection.viewSelected}
                onToggleSelectAll={selection.toggleSelectAll}
                onClearSelection={selection.clearSelection}
              />
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-4">
        <div className="mx-auto max-w-3xl">
          <ul className="space-y-2">
            {items.map((item) => (
              <RawMessageRow
                key={item.id}
                item={item}
                selected={selection.selectedIds.has(item.id)}
                onToggleSelect={selection.toggleSelect}
                onDropEvent={dropEvent}
                onMoveEvent={moveEventToTrack}
                onApplyTrack={applyTrack}
                onSetNotice={setNotice}
              />
            ))}
          </ul>

          {!loading && items.length === 0 && (
            <div className="py-10 text-center text-xs text-slate-500">
              Нічого не знайдено.
            </div>
          )}

          <div ref={sentinelRef} className="h-10" />
          {loading && (
            <div className="py-4 text-center text-xs text-slate-500">
              Завантаження…
            </div>
          )}
          {done && items.length > 0 && (
            <div className="py-4 text-center text-xs text-slate-600">
              Це все.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
