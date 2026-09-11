# Phase 27 — Continuous knowledge intelligence

**Status: COMPLETE.** 15 dedicated tests, all nine suites green.
**This closes the SOW's 27 implementation phases at the build level.**

Two questions almost nobody asks of their own notes:

```
secondbrain gaps    what does this store NOT know, and how would I close it?
secondbrain meta    what does this store know about ITSELF?
```

---

## §73 — Gaps

Every knowledge system can list what it holds. Almost none will tell you what
is missing, because absence never raises an exception — which is the same
blindness that let a staging deploy die in June and get noticed in September.

So **every gap is counted and comes with the action that closes it.** A gap you
cannot count is an anxiety, not a finding. Live output:

| Severity | Gap | Count |
|---|---|---:|
| HIGH | files named in conversations whose bytes were never exported | 2,147 |
| HIGH | URLs where only the address and title were captured, never the page | 1,448 |
| HIGH | whole sources named in the SOW, never acquired | 10 |
| MEDIUM | objects with no readable body (excluding by-design classes) | 4,785 |
| MEDIUM | months inside the corpus span where nothing was captured | 25 |
| MEDIUM | items isolated in the dead-letter queue | 11 |
| INFO | bodies withheld because they held credentials | 696 |
| INFO | ranking signals declared but not contributing | 2 |

**The empty-body gap is the design point.** The raw number is 6,932, which
reads as a catastrophe. Broken down, 2,147 are `FileReference` objects that
have no body *by design* — the export named the file and never carried its
bytes. So the gap reports 4,785 **unexpected** empties with the by-design
classes named and excluded. An aggregate that frightens without directing is
worse than silence.

Gaps with a count of zero are **not** reported. A list padded with
"0 conflicts, 0 failures" trains you to skim it.

---

## §74 — Meta

What the store knows about itself, on the live corpus:

```
scale        39,766 objects · 40,222 versions · 65,796 relationships · 5.9 GB
state        ORIGINAL 38,652 · DERIVED 1,074 · SYNTHESIZED 39 · HUMAN_VALIDATED 1
voice        first-hand 9,998 (25.1%) · machine-generated 8,610 (21.7%)
provenance   38,652 acquired objects, 38,652 tracing to raw bytes — 100.00%
             0 untraceable · 1,114 derived (traced via parents)
read/write   4 inquiries · 10 objects ever surfaced · 0.025% of the store
```

**Two of these are worth staring at.**

*100.00% traceable, 0 untraceable.* The §17 promise — answer → object → version
→ provenance → evidence blob → bytes — holds for every acquired object in the
store. Not sampled. Counted.

*0.025% ever surfaced.* Of 39,766 objects, ten have ever been returned in
answer to a question. This is the number that says whether a second brain is
being **used** or merely **filled**, and almost no note system will show it to
you. `ask` now records which object ids it surfaced, precisely so that this
stays answerable.

---

## Two bugs the numbers caught

**A percentage over 100.** The first run reported *100.1% traceable*. That is
the arithmetic saying the numerator and denominator describe different
populations — some `DERIVED` objects do carry an `original_hash`, so
"objects with a blob" ÷ "objects minus derived" was comparing two different
sets. Both figures are now computed over the same population, and a test
asserts `traceable + untraceable == acquired`. An impossible ratio is a gift:
it is a bug that announces itself.

**A metric that lied by omission.** `read_vs_write` reported *0 objects ever
surfaced* across 2 inquiries — technically true, because id logging had only
just been added and those inquiries predated it. It now reports how many
inquiries lack ids and states plainly that the figure undercounts. A metric
that is silently incomplete is worse than one that is absent.

---

## Where this leaves the SOW

All 27 implementation phases now have working code at the build level. What
remains is **not building** — it is acquisition (source exports only Moiz can
request) and the operational items in `NEXT-STEPS.md`.

Two things remain deliberately unimplemented and say so on every run:
`personal_relevance` (needs a labelled benchmark; inventing a weighting would
be unfalsifiable) and `historical_importance` (needs Phase 7 over the full URL
corpus — 1,448 of ~20,000 ingested). Backup **retention** is likewise absent:
deleting old backups needs the §97 gate done properly, not bolted on.
