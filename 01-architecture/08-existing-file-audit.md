# 8. Existing "2,000-File" Audit

**SOW §110 Phase 3 · Status: `PARTIALLY_COMPLETED` — the premise did not survive measurement**

## The finding

The SOW asserts ~2,000 existing files as a known corpus. **That corpus was not located where it was expected, and the number is not supported by anything measured.**

| Location | Files | Knowledge content |
|---|---:|---|
| Connected project folder | 526 total | **~29 top-level files, 8,389,738 B** — the rest is the `automsp-outreach-analytics` app plus Playwright `node_modules` |
| Project folder, dependency-pruned | **150** | 81 knowledge objects + 69 classified-excluded code/binary |
| Downloads INCLUDE set | 17,312 | far more than 2,000, and a different population |

So the reachable corpus is either **~150** (project folder, pruned) or **17,312** (Downloads INCLUDE) depending on which population is meant. Neither is 2,000.

## Where the 2,000 probably are

~90 home folders were never mounted: `Documents`, `Desktop`, `OneDrive`, `AutoMSP`, `bos-fable-5-work`, `automsp-obsidian-vault.git`, `Recorded Calls`, `Pictures`, `source`, `frontend`. The Obsidian vault in particular — prior context describes it as the second-brain content source, synced to `auto-msp/automsp-obsidian-vault`.

**This is a folder-grant question, not a research question.** One grant resolves it.

## What was actually audited

All 150 pruned project-folder files, with SHA-256 on every one, ingested into the canonical store:

| Result | Value |
|---|---:|
| Knowledge objects created | **81** |
| Classified EXCLUDE (counted, not dropped) | **69** (731,515 B) |
| Failures | **0** |
| Provenance rows | 1 per version, 100% |
| Evidence blobs, re-hash verified | 74, **0 missing / 0 corrupt** |

The corpus is substantive strategy and architecture material: the AI Operating System Doctrine (29 KB), Throughline Service Blueprint (292 KB), Fable5 Analysis Prompt Library (46 KB), Outreach Analytics Dashboard Spec (82 KB), LinkedIn Authority Engine spec, Revenue Intelligence Scorecard, Continuous Improvement Framework, plus nine `.docx` GTM deliverables and an `.xlsx` baseline worksheet.

## Duplicate finding that changes a deletion decision

`automsp-outreach-analytics.stale-backup` reads as obviously redundant and **is not**: 108 files vs 367 in the live folder, 107 common paths, **89 byte-identical (82.4%)**, **18 genuinely drifted** — including `src/js/app.js`, `charts.js`, `data.core.js`, `dist/index.html` and `docker-compose.yml` — and one file present only in the backup, `.git/_stale_index.lock`, which explains how it got its name.

Deleting it on the strength of "82% identical" would silently lose 18 real divergences. This is the §19/§125.10 rule earning its place: **link duplicates, never delete them.**

## Open items

1. **Grant access to the home folders** — the highest-value single action for this phase.
2. 4,447 extensionless files (566 MB) plus 166 `.dot` and 31 `.excalidraw` were auto-excluded by extension heuristic and need a content-sniffing pass; some are likely diagrams worth keeping.
3. Archive interiors (2.99 GB in the project folder) are unexamined.
4. Downloads bulk ingest is `READY` but unrun — 17,312 INCLUDE files inventoried, not yet canonicalized.
