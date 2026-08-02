---
name: analyze-feed
description: Analyze a Kyiv Live Radar feed export (the JSON from Адмінка → Весь фід → Експорт, or any dump of raw_messages) to find what the parser missed, what it wrongly surfaced, and which fixes are worth making. Use this whenever the maintainer pastes or points at feed/raw-message JSON, or asks to "проаналізуй фід", "що ми пропустили", "чому парсер це не побачив", "звідки цей false positive", "покращити парсер", "чого не вистачає в експорті" — and also when they describe a bad night on the map (split tracks, phantom targets, a stuck alert, a wrong card in the feed) and the evidence would come from the feed. Assume this skill applies to any question about parser/tracking accuracy on real messages, even without the word "фід".
---

# Analyzing a feed export

The point of this is not to describe the export. It is to turn one night of real
messages into a short list of changes worth making — and to be right about them,
because every "fix" to this parser is a change to what a person sees on a map
during an air raid.

Two failure modes to avoid. **Fabricating a cause**: the export shows what
happened, not why, and the parser is easy to run — so verify instead of
reasoning. **Recommending work that was already decided against**: several
tempting "improvements" here are deliberate choices, at least one made after a
live failure. `references/failure-taxonomy.md` lists both the code map and those
decisions; read it before proposing anything.

## 1. Get the export into a file

The maintainer usually pastes JSON straight into the chat. Write it to a file in
the scratchpad first (a 100-message dump is large; re-reading it inline burns
context for nothing). If they gave a path, use that.

The export is either a bare list or an envelope with `.messages` — the script
handles both, and tolerates older dumps missing the newer fields.

## 2. Run the mechanical pass

```bash
python3 .claude/skills/analyze-feed/scripts/feed_report.py <export.json> --texts
```

Plain `python3`, no venv. It counts outcomes per channel, splits LLM spend
between the two paths, flags out-of-order storage and unthreadable reply chains,
and lists track fan-out, type churn and every message that produced nothing.

Read its output as a set of pointers. It deliberately does not judge: "9 tracks
in one incident" is correct for a ballistic salvo and wrong for a single drone,
and only the texts settle it.

## 3. Read the messages the counts point at

Now spend attention where the numbers said to. Go through the silent messages
and the anomalies in order, and for each one ask what a person watching the map
would have wanted to see at that moment.

The one habit that matters: **when you form a hypothesis about why the parser
did something, run the parser.** It takes seconds and it has repeatedly
overturned a confident guess.

```bash
cd backend && .venv/bin/python -c "
import sys,asyncio; sys.path.insert(0,'.')
from app.parsing.rules import parse_message
from app.parsing import DistrictMatcher
from app.pipeline.ingest import should_fallback
from app.db import SessionLocal
from sqlalchemy import select
from app.models import District
async def main():
    async with SessionLocal() as s: ds=list(await s.scalars(select(District)))
    m=DistrictMatcher(ds)
    for t in ['<message text>']:
        r=parse_message(t,m)
        print({k:v for k,v in vars(r).items() if k!='raw_text' and v not in (False,None,'',[])})
        print('fallback:', should_fallback(r))
asyncio.run(main())"
```

When the export can't answer something (which incident a track belonged to, what
the neighbouring messages were, whether an alert was open), query
`backend/kyiv_radar.db` with `sqlite3` — it is the same schema as prod, and row
`id` order is storage order, which is how out-of-order ingestion was originally
found.

## 4. Classify each finding

Every finding should end up as one of:

- **False positive** — surfaced, shouldn't have. Almost always a missing phrase
  in a suppression filter; cheap and safe to fix.
- **False negative** — real, dropped. Usually gazetteer coverage or a class the
  rules have no concept of yet.
- **Grouping** — the sightings were right, the tracks weren't.
- **Ordering** — the message arrived late and the pipeline treated it as fresh.
- **Cost** — an LLM call that bought nothing.
- **Working as intended** — say so plainly and move on. This is a real category
  and using it well is what makes the rest credible.

Attach the evidence to each: message ids, the text, what the parser actually
returned, and the file:line where the behaviour lives.

## 5. Report

Lead with the counts table, then the findings ranked by how much a person on the
map is hurt by them — not by how easy they are to fix. For each finding give:
what happened (with the real message quoted), why (verified, not guessed), where
in the code, and roughly what the fix costs.

Close with a ranked list of what to do, and say which findings you are NOT
proposing to act on and why. A short honest list beats a long speculative one.

If a finding contradicts something in `references/failure-taxonomy.md`, say so
explicitly rather than quietly proposing to undo a past decision — the decision
may still be wrong, but it deserves an argument, not a silent reversal.

## 6. If asked to implement

Then, and only then:

- Suppression-filter and vocabulary changes: add the phrase, add a test with the
  real message that motivated it, run `pytest` and `eval/run_eval.py`.
- Anything touching `app/domain/tracking.py` or grouping: run
  `eval/track_eval.py` before and after and quote both numbers. Grouping was
  tuned by measurement; changing it by argument alone has regressed it before.
- Gazetteer entries: geocode via `scripts/geocode_localities.py` and sweep the
  real corpus for stem collisions before committing.
- Pydantic schema changes: regenerate both ends (`scripts/dump_openapi.py`, then
  `npm run gen:types`) or CI fails.

Do not commit or push — the maintainer tests locally and gives the go-ahead
(`/do-release` is the only exception).

## If the export is missing something you needed

That is itself a finding worth reporting. The export is meant to make a dump
self-explanatory without a DB session; `suppressed_by`, per-event district,
the `parsed` snapshot, `ingested_at` and `reply_parent_raw_id` were all added
because an analysis stalled without them. Say what you had to reconstruct by
hand and what field would have saved it.
