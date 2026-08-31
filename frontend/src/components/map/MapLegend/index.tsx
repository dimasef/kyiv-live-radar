import { Info } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { safeGet, safeSet, STORAGE_KEYS } from "@/lib/storage";

import { mapControlClass } from "../controlStyles";
import { legendRows, type LegendRow } from "./rows";
import SourceLinks from "./SourceLinks";

function initialOpen(): boolean {
  return safeGet(STORAGE_KEYS.legendOpen) === "1";
}

/** An inline SVG (glyph or swatch) used for a legend row. */
function Swatch({ html }: { html: string }) {
  return (
    <span
      className="inline-flex h-6 w-6 flex-none items-center justify-center"
      aria-hidden
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function Row({ row }: { row: LegendRow }) {
  const { t } = useTranslation();
  const [flipped, setFlipped] = useState(false);
  const shown = flipped && row.flipped ? row.flipped : row;

  const content = (
    <>
      <Swatch html={shown.html} />
      <span className="truncate first-letter:uppercase">{t(shown.labelKey)}</span>
    </>
  );

  if (!row.flipped) {
    return <li className="flex items-center gap-2.5 px-1.5 py-1 text-[14px]">{content}</li>;
  }
  return (
    <li>
      <button
        onClick={() => setFlipped(!flipped)}
        aria-pressed={flipped}
        className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1 text-left text-[14px] transition-colors hover:bg-white/[0.06]"
      >
        {content}
      </button>
    </li>
  );
}

/** Collapsible legend — what a marker's shape and colour mean. Positioned by
 * MapControls, not by itself. */
export default function MapLegend() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(initialOpen);

  const toggle = () => {
    safeSet(STORAGE_KEYS.legendOpen, open ? "0" : "1");
    setOpen(!open);
  };

  return (
    <div className="relative">
      <button
        onClick={toggle}
        aria-label={t(open ? "legendCtl.hide" : "legendCtl.show")}
        aria-expanded={open}
        className={mapControlClass(open)}
      >
        <Info size={17} />
      </button>
      {open && (
        <div className="scroll-slim absolute bottom-full left-0 mb-2 flex max-h-[68vh] w-64 flex-col gap-2 overflow-y-auto">
          <SourceLinks />
          <div className="panel popover-up p-3 text-slate-300">
            <span className="panel-title mb-2 block px-1.5">{t("legend.title")}</span>
            <ul className="space-y-0.5">
              {legendRows().map((row) => (
                <Row key={row.id} row={row} />
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
