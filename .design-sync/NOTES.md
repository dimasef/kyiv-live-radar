# design-sync notes — Kyiv Live Radar

Repo-specific gotchas for future syncs. Read before re-syncing.

## Shape: `package` on a PRIVATE app (not a component library)

`frontend/` is a private Vite app with **no shipped `.d.ts` exports and no lib
entry**. So this sync is deliberately off the beaten path:

- **Entry** is a hand-written barrel `frontend/.ds-entry.tsx` (gitignored) that
  re-exports the 17 curated presentational primitives as named exports. Passed
  via `--entry`. Do NOT let the converter synth-entry the whole `src/` — it
  `export *`s side-effecting modules (main.tsx → ReactDOM.render) and breaks
  previews.
- **Component list** comes SOLELY from `cfg.componentSrcMap` (the app has no
  `.d.ts` exports, so nothing is auto-discovered). To add/remove a component,
  edit BOTH the barrel and `componentSrcMap`.
- **i18n**: the barrel's first import is `import './src/i18n'` — this
  initializes i18next on the BUNDLE's own react-i18next instance so components
  render real Ukrainian text (not raw keys). A preview-side i18n import would
  hit a different instance and do nothing.

## cssEntry is a regenerated copy — refresh it on re-sync

`cfg.cssEntry` = `frontend/.ds-app.css` (gitignored), a COPY of the app's
compiled Tailwind CSS with a Google-Fonts `@import` prepended. It must live
INSIDE `frontend/` (cssEntry is bounded to the package dir, not the repo root).
**Regenerate every re-sync:**

```sh
cd frontend && npm run build
FONT="@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=Unbounded:wght@500;700&display=swap');"
printf '%s\n' "$FONT" | cat - dist/assets/index-*.css > .ds-app.css
```

## Dark theme — previews stage themselves

Components are designed for the ink-950 (`#05080d`) background. The card harness
(`lib/emit.mjs`) forces `body{background:#fff}` and is not forkable, so every
preview wraps its content in `.design-sync/previews/_stage.tsx` `<Stage>` (a dark
ink surface). Keep this for any new preview or it renders low-contrast on white.

## Known render warns (benign — do not chase)

- `[RENDER_THIN] FilterSelect: variants render identically` — a native
  `<select>`; Default/Selected differ only by the chosen option text.
- `TypeGlyph` occasionally flags thin — its glyphs are 15px SVG icons (no text).

## Excluded

- `UpdateToast` — imports `virtual:pwa-register/react` (a Vite virtual module
  esbuild can't resolve); it's PWA plumbing, not a design primitive.

## Re-sync risks

- **Fixtures** in `.design-sync/previews/_fixtures.ts` mirror `frontend/src/types.ts`
  (Threat / Notice / Incident / Alert / JournalDay / ThreatEvent). If those
  interfaces change, fixtures may need updating (TS errors surface at preview
  compile).
- **Fonts** load remotely from Google Fonts (`[FONT_REMOTE]`) — offline/headless
  renders fall back to system fonts; not shipped in `fonts/`.
- The compiled-CSS filename is content-hashed and changes each app build; the
  `cp … index-*.css` glob above handles it.
