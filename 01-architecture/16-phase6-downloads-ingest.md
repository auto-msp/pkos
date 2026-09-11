# 16. Phase 6 — Downloads Ingestion

**SOW §75, §110 Phase 6 · 2026-09-08 · Status: `COMPLETED` with reconciled exceptions**

## Completion proof (§43)

```
SOURCE:        laptop filesystem — Downloads
DISCOVERED:    57,145 files / 11.05 GiB (W1 inventory, walked to completion)
IN SCOPE:      17,312 files / 6.31 GB  (SOW 75 INCLUDE)
INGESTED:      16,435 under Downloads + 81 from the project folder = 16,516 File objects
EXCLUDED:      39,833 files / 4.74 GB  — classified, counted, never deleted
FAILED:        0
VALIDATION:    PASSED — 9/9 invariants
STATUS:        COMPLETED
```

### Canonical store, after

| | |
|---|---:|
| Canonical objects | **17,967** |
| Versions / provenance / events | **18,014 each** (1 : 1 : 1) |
| Files / Bookmarks / Servers | 16,516 / 1,448 / 3 |
| Evidence blobs | **9,035 — 5.70 GB** |
| Duplicate alias links | **7,485** |
| Acquisition jobs | 76 |
| Dead-letter items | 11 (malformed bookmark URLs) |
| Audit records | 129 |
| JSONL mirror | **109,871 rows, 283 MB, 26 tables** |

## Content addressing deduplicated 45% of the corpus for free

16,516 File objects resolve to **9,035 distinct blobs**. 7,481 files are byte-identical to another file, so the evidence plane stored each set of bytes once: **6.31 GB logical → 5.70 GB stored**.

Explicit dedup analysis then found **3,367 exact groups / 7,476 redundant objects / 630.1 MB**, and wrote **7,485 alias links**. Nothing was deleted — every alias keeps its own provenance and remains queryable (§19, §125.10). W1's earlier estimate of 1,037 groups was a floor: it used partial hashing and skipped files under 20 KB. Full SHA-256 over every file more than tripled it.

## Count reconciliation — 960 not ingested, 942 explained

| Reason | Files |
|---|---:|
| Inside a hidden directory the adapter prunes | 847 |
| The `AutoMSP BOS Claude Project` folder — deliberately skipped, already ingested via its own mount | 70 |
| Inside a dependency directory (`node_modules`, `.git`, …) | 25 |
| **Classifier disagreement — see below** | **18** |

### The 18: two classifiers, ~0.1% disagreement

Not a fault — a genuine difference between W1's inventory classifier and the adapter's `INCLUDE_EXT` map. Extensions W1 counted as INCLUDE that the adapter does not recognise: `.ico`, `.ogg`, `.tgz`, `.skill`, plus some very long Instagram export filenames.

**The disagreement runs both ways**: 83 files the adapter ingested were marked EXCLUDE by W1 — mostly `.md` files inside directories W1 treated as code repositories (`hermes-ai-team/README.md`, `AGENTS.md`, `ROADMAP.md`).

This is worth resolving rather than papering over, because it is exactly the §75 boundary question: **is a README inside a code repo knowledge or build artefact?** The adapter says knowledge (it is prose); W1 said artefact (it is inside a repo). Both are defensible. One list should win, and the choice should be recorded rather than emergent from two independently written extension maps.

Net: **83 in, 18 out** against W1's classification — under 0.6% of the corpus either way.

## Two engineering findings from running at real scale

**1. Resume was as expensive as the first run.** The adapter hashed every file before discovering it was unchanged, so a restarted ingest cost full price. Added a fast path that compares size + mtime against the recorded `source_object` and skips the hash when both match. Effect on a real directory: **125 s → 3.8 s**. This is a resume optimisation, not a weakening of §18 — `validate --deep` still re-hashes every blob and reports drift.

**2. The derived plane could not be created on the canonical store's filesystem.** SQLite cannot create a *new* database on this mount at all: its first commit must delete a rollback journal, and unlink is forbidden here. It surfaces as an opaque `disk I/O error`. The existing `canonical.sqlite3` survives only because it is already in WAL mode, which never deletes a journal.

The fix was not to weaken the canonical layer to suit an index. The derived plane is `PKOS_DERIVED`-configurable and now lives on local scratch. That is the intended shape rather than a workaround — §22 class D says derived data is never synchronised and always regenerated, so it belongs on fast local storage while canonical sits on durable, synced, possibly restricted storage. `secondbrain rebuild-index` reconstructs it in 42 s from canonical content.

Artefacts SQLite left behind that cannot be unlinked here were moved to `02-canonical/pkos-store/derived/_unusable-on-this-mount/` — safe to delete from Windows.

## Retrieval, working on the real corpus

FTS index: **10,482 objects** — aliases correctly excluded. Sample results:

- `voice agent pricing` → `value-ladder.md` (score 14.5), surfacing a real bundle price
- `second brain provenance` → `# MASTER PROMPT - Second Brain.txt` (score 20.1) — **an earlier draft of this project's own specification, found in the corpus**
- `n8n workflow automation` → `a008-seo-content-briefs.md`, `technical-infrastructure-devops.md`

Four of the nine §72 ranking signals remain `NOT_IMPLEMENTED` and are declared as such: semantic relevance, graph connectivity, personal relevance, historical importance. All four need Phases 22–23.

## Phase status after this run

| Phase | State |
|---|---|
| 3 — existing-file audit | `PARTIALLY_COMPLETED` — home folders still unmounted |
| 4 — canonical storage | `COMPLETED` |
| 5 — provenance / versioning / manifests | `COMPLETED` |
| **6 — Downloads ingestion** | **`COMPLETED`** |
| 7 — historical web | `PARTIALLY_COMPLETED` — 1,448 URLs; browser profiles still unmounted |
| 8 — bookmarks | `COMPLETED` for the Aug-2026 export |

Not yet run: `validate --deep` over all 9,035 blobs. At the measured read throughput that is roughly 20–25 minutes and exceeds a single call; it should be run once as a background job on the server, not through this bridge.
