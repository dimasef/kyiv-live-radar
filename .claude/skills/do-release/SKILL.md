---
name: do-release
description: Ship a prod release of Kyiv Live Radar — summarize the work since the last release, add the mandatory CHANGELOG entry, verify the build, then commit and push. Use when the maintainer runs /do-release or asks to "зробити реліз"/"випустити"/"cut a release". Running this IS the explicit go-ahead that overrides the normal "do NOT auto-commit or push" rule.
---

# /do-release — cut a Kyiv Live Radar release

Invoking this skill is the maintainer's explicit **«пуш»** — it is the one
sanctioned exception to the "do NOT auto-commit or push" working agreement. It
commits and pushes on its own. Everywhere else, still stop at the diff.

Work through these steps in order. Do not skip the verification step, and do not
push if it fails — report and stop.

## 1. Gather what changed

- `git status` + `git diff` (and `git diff --staged`) for the uncommitted work.
- `git log --oneline -15` to see the last release's version/commit for context.
- Skim the current conversation for intent the diff alone doesn't show (the
  *why*, not just the *what*).

From that, write a short human summary of the release for yourself, then turn it
into the changelog entry below.

## 2. Add the CHANGELOG entry (mandatory)

**Every prod release MUST add a `CHANGELOG` entry** in
`frontend/src/changelog.ts`. `APP_VERSION` is derived from the newest entry (the
`LATEST` literal) and shown in-app (Settings → version history at `/change-log`).
Never ship a user-visible change without one.

Each entry requires:
- `date` — `YYYY-MM-DD`, the release day (today).
- `kind` — per `SEMVER_RULES` in that file:
  - `patch` = fix/tweak with no new capability (parser/gazetteer fixes, dedup,
    cosmetics).
  - `minor` = new operator-visible capability (new threat type, map layer,
    incident, feed info). A new **admin** capability is still a `minor`, even
    when its visible blurb is small (see the visibility rule below).
  - `major` = public/breaking (stays 0 during the MVP).
- `changes` — Ukrainian, operator-facing (what they'll notice), **not** internal
  mechanics.

Bump `LATEST` to the new version and put the new entry **first** (newest-first
order). Keep `LATEST` equal to the newest entry's `version`.

### The changelog is visible to EVERY user — do not leak

The changelog is **not** gated by role: regular non-admin users read it too. An
entry must never reveal anything a regular user shouldn't know:

- No mention of admin-only tools/tabs (e.g. the `/admin` console).
- No exposure of the system's fallibility or inner workings — that the parser
  mis-recognizes threats, that a human manually corrects data, internal
  thresholds, backend mechanics.

For an **admin-only feature**, describe only the effect a regular user could
genuinely perceive (e.g. «мапа лишається чистішою») and omit how/by whom — or,
if there is no such perceivable effect, keep the entry minimal and generic
rather than revealing the feature. The `kind`/version bump still reflect the
real release even when the visible `changes` text is small.

## 3. Verify the build

The changelog and any shipped code must type-check/build:

```bash
cd frontend && npm run build      # tsc -b && vite build — this IS the type-check
```

If the backend changed, also run its suite:

```bash
cd backend && .venv/bin/pytest tests/ -q
```

If anything fails, **stop** — fix or report, do not commit/push.

## 4. Commit and push

Releases go on `main` (that's how this repo ships — recent history is direct
commits to `main`). Stage everything for the release and commit with a message
whose subject is the new version + a short Ukrainian title mirroring the
changelog entry, e.g.:

```
0.14.0: точніша мапа
```

End the commit message body with the trailer:

```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

Then push:

```bash
git push origin main
```

## 5. Report

Tell the maintainer: the new version, the `kind`, the one-line changelog, and
confirmation that build/tests passed and the push landed (`git log --oneline -1`).
Deployment is automatic (backend → Railway, frontend → Vercel).
