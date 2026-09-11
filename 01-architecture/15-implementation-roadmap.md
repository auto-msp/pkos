# 15. Implementation Roadmap

**SOW §110, §111 · Ordering revised where evidence showed a safer sequence, as §110 permits.**

## Where things stand

Phases 4 and 5 — canonical storage, provenance, versioning, manifests — are **done and running**, ahead of their nominal order. That happened because they need no external access, and they are what makes everything else safe. Phases 1 and 2 are blocked on physical reachability, not on effort.

## The critical path is three unblocks, none of which are engineering

| # | Action | Unblocks | Effort |
|---|---|---|---|
| **U1** | Run `pkos-server-audit.sh` on each server, drop JSON in `90-evidence/servers/` | Phases 1, 2; deliverables 4-7; the sync authority decision | ~5 min/server |
| **U2** | Grant the `AppData` folder (or export Chrome/Edge history) | Phase 7 at real scale — the missing ~18,500 URLs | one grant |
| **U3** | Grant the remaining home folders (`Documents`, `OneDrive`, `AutoMSP`, the Obsidian vault…) | Phase 3 properly — the actual "2,000 files" | one grant |

Everything downstream is gated on these. They cost minutes; the work they unblock costs days.

---

## Wave 1 — unblock and consolidate

**W1.1 Server audit (U1)** → ingest → `secondbrain servers` renders the §102 matrix → deliverables 4-7 become real. *Gate: every server reports `COMPLETED` or an explicit `BLOCKED` reason.*

**W1.2 Storage remediation plan (Phase 2).** From audit evidence only. Full §97 gate: discover → dry run → impact report → dependency analysis → backup check → **your approval** → execute → validate → audit. Known trap: the Voicebox container's undeclared Docker-network attachment on `132.145.133.39` — a naive "unused network" cleanup breaks a working service.

**W1.3 Rotate the leaked credentials.** Independent of everything else and overdue: 9 NVIDIA NIM keys, a proxy key and an OpenRouter key were pasted in plaintext in a prior session. Revocation is unconfirmed. Treat as compromised until each is confirmed rotated.

**W1.4 Clean up the dead cron entries.** Two "Apollo Prospecting Queue" jobs on `150.136.95.118` fire every 4 hours at a script that no longer exists, failing silently every time. Either restore the script or remove the entries — and given an unattended job once consumed an entire LLM subscription, decide deliberately rather than leaving them. *Nothing here is enabled or scheduled without your explicit say-so.*

**W1.5 Backup before anything destructive (§92, §93).** `secondbrain backup <dest> --include-evidence` then `secondbrain restore --verify <backup>`. A backup is not valid until a restore has been verified — the verify command already implements exactly that check. **No cleanup runs before this passes.**

## Wave 2 — the corpus that is already reachable

**W2.1 Downloads bulk ingest (Phase 6).** 17,312 INCLUDE files, ~6.78 GB. The adapter is built and idempotent; this is a run, not a build. Budget evidence-plane growth accordingly — that number decides rsync vs object storage in the sync design.

**W2.2 Home folders (Phase 3, after U3).** Locate the real 2,000-file corpus, and the Obsidian vault in particular.

**W2.3 Browser history (Phase 7, after U2).** Read `History` / `places.sqlite` read-only. Ingest the second bookmarks file **separately** — different machine, different history, must not be deduplicated away.

**W2.4 Claude conversation exports (Phase 14, early).** Promoted from its nominal position because **the evidence is already on disk** — 121 MB current-generation plus a 68 MB older generation. §68: preserve the raw conversation *and* extract knowledge from it; keep both generations (§67 superseded ≠ deleted).

**W2.5 Extensionless triage.** 4,447 files (566 MB), 166 `.dot`, 31 `.excalidraw` auto-excluded by extension. Content-sniff and reclassify. Good agent work — genuinely ambiguous.

**W2.6 Archive interiors (§51).** List, never extract-in-place. 2.99 GB in the project folder alone.

## Wave 3 — external sources, one at a time (§41)

Strict checkpointing: the next source does not start until the current one reaches `COMPLETED`, `PARTIALLY_COMPLETED` or an explicit `BLOCKED`.

Order by *value ÷ friction*: **Airtable** (connector live, deferred, cheapest to resume) → **Google Sheets/Docs via Takeout** (not the connector — formulas) → **Notion** → **Email** (account discovery *first*, §46) → **GitHub Stars** (needs a route around the proxy) → **Gumroad** → **social exports**.

Each gets the §99 adapter set — discovery, acquisition, parser, normalizer, enricher, validator — on the framework that already exists.

## Wave 4 — the parts that make it a second brain

Only after the corpus is real:

**Phase 22 knowledge graph** — entity resolution, then relationships. The tables exist and are populated by adapters; traversal and resolution are the work.
**Phase 23 hybrid retrieval** — semantic and graph signals to complete §72 ranking. Four of nine ranking components are currently `NOT_IMPLEMENTED` and declared as such.
**Phase 24 agent layer** — per deliverable #13: bounded, read-mostly, interpretation only.
**Phase 25 sync** — canonical authority to the server; the laptop becomes the replica it is supposed to be.
**Phase 26 backup/DR** — layered primary + secondary + off-site + versioned, with scheduled restore tests. RAID is redundancy, never backup.
**Phase 27 continuous intelligence** — §73 knowledge gaps, §74 meta-knowledge.

## Benchmarks (§104) — write them early, not last

Real questions, with known answers, from your own material:

- "When did I first research SAP?" — answerable now: 2018-2026 bookmark corpus.
- "Which tools have I investigated repeatedly?" — answerable now: 928 domains with visit counts.
- "What happened in 2021?" — the corpus shows 4 bookmarks in a year. Real dormancy, or a missing data source? **This is a benchmark question whose answer also validates the corpus.**
- "Why does SAP dominate a corpus that should look like AutoMSP?" — a genuine §74 signal, unexplained.
- "What evidence supports the AI Operating System doctrine?" — cross-source, needs the graph.

Benchmarks written now can measure every later phase. Written at the end, they measure nothing.

## Phase gate (§111) — applied to every wave

Discovery complete **and** data understood **and** dependencies understood **and** security conditions satisfied **and** backup conditions satisfied **and** validation passed — before the next phase starts.

`secondbrain validate` mechanizes the last one. The rest are judgement, and they are yours.
