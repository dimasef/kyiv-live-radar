# Kyiv Live Radar — "ops-console" design system

A dark, tactical situational-awareness UI: deep ink layers, a phosphor-cyan
accent, and a shared status palette. Components are React, styled with
**Tailwind utility classes** (a custom preset), and are **designed for a dark
background** — always place them on an ink surface, never on white.

## Wrapping & setup

There is no provider to mount — components are self-contained. The one hard rule
is the **background**: wrap any screen or card in the ink surface, or light-on-
dark text renders invisible.

```jsx
import { StatusChip, BannerShell } from '<pkg>'

<div className="min-h-screen bg-ink-950 font-sans text-slate-200 p-4">
  <BannerShell tone="alert" color="#ef4444" role="alert" label="Тривога"
               expanded={false} onToggle={() => {}}>
    <span>Повітряна тривога</span>
    <span className="font-mono tabular-nums opacity-90">18:24</span>
  </BannerShell>
</div>
```

Text is Ukrainian by default (the bundle initializes i18next; `LanguageSwitcher`
toggles uk/en).

## Styling idiom — Tailwind with this preset's palette

Style your own layout glue with Tailwind classes. Use THIS preset's names:

| Family | Real class names |
|---|---|
| Surfaces (bg) | `bg-ink-950` `bg-ink-900` `bg-ink-850` `bg-ink-800`, panels `bg-white/[0.03]` |
| Accent | `bg-phosphor` `text-phosphor` `text-phosphor-soft` `border-phosphor/40` (phosphor = `#22d3ee`) |
| Status (semantic — don't restyle) | `confirmed` `#ef4444`, `unconfirmed` `#eab308`, `destroyed` `#6b7280`, `clear` `#22c55e`, `conflict` `#f97316` |
| Text | `text-slate-200` (body) `text-slate-300` `text-slate-400` (dim) `text-slate-500/600` (mono labels) |
| Fonts | `font-display` (Unbounded, headings) · `font-sans` (IBM Plex Sans, body) · `font-mono` (IBM Plex Mono, times/counts) |
| Borders/hairlines | `border-white/10` `border-white/[0.08]` |

CSS variables are also available: `var(--bg)` `var(--phosphor)` `var(--phosphor-soft)`
`var(--text)` `var(--text-dim)` `var(--panel)`.

## Where the truth lives

- **Styling**: read `styles.css` and its `@import` of `_ds_bundle.css` (the
  compiled Tailwind + the `:root` token block).
- **Per-component API**: each `components/<group>/<Name>/<Name>.d.ts`. Several
  components take **real domain objects** — `StatusChip`/`TypeGlyph` a `Threat`,
  `NoticeCard` a `Notice[]`, `AttackSummaryCard` an `Incident`, `AlertSegment`
  an `Alert`, `CalendarHeatmap` a `Map<string, JournalDay>`. Read the `.d.ts`
  and match the shape; don't pass loose strings.

## Idiom at a glance

Small primitives carry their own color: `StatusChip` (impact/destroyed/lost
pills), `LlmTriageBadge` / `OutcomeBadge` (tinted category chips), `Switch`
(phosphor toggle). Feed cards (`NoticeCard`, `AttackSummaryCard`) are tinted
left-border panels. Banners (`BannerShell`, `AlertSegment`) are pill-shaped and
tone-driven. Compose them on `bg-ink-950`.
