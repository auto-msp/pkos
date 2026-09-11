# 10. Synchronization Architecture

**SOW §21–§25 · Status: `DESIGNED`, implementation `BLOCKED` on the server audit**

`secondbrain sync` deliberately exits 3 with NOT_IMPLEMENTED. Designing a sync topology for infrastructure nobody has measured would be guessing, and sync bugs corrupt canonical data.

## 10.1 Authority

**The Ubuntu server holds canonical authority. The laptop is a first-class working replica. GitHub is neither.** (§21.1)

Today that is inverted — the only store is on the laptop, at `pkos/02-canonical/pkos-store/`. That is a temporary, acknowledged deviation, and the server audit is what resolves it. Which server becomes the authority is a decision the audit informs: it needs adequate free space (§48 flags anything ≥70% used), a backup path, and it should probably *not* be the box already running n8n, Caddy and Voicebox on contended storage.

## 10.2 Five sync classes (§22) — different data, different mechanisms

| Class | Content | Mechanism | Conflict handling |
|---|---|---|---|
| **A** canonical text | `canonical/mirror/*.jsonl`, schemas, ontology, prompts, adapters, docs | **Git** | 3-way merge + provenance + human review |
| **B** structured DB | `canonical.sqlite3` | **DB-level replication/export — never a Git file** | record-level identity + version + conflict rows |
| **C** binary/large | `evidence/blobs/**` | object storage / rsync, **append-only** | none possible: content-addressed, immutable |
| **D** derived | `derived/**` | **do not sync — regenerate** | n/a |
| **E** secrets | credentials, tokens, keys | **never synced through Git** | n/a |

Class B is the one people get wrong. A SQLite file in Git is a binary blob that cannot merge; two divergent copies mean one is silently lost. The JSONL mirror exists precisely so Git tracks Class A text while the database syncs by its own mechanism.

Class C needs no conflict resolution at all — a content-addressed store cannot conflict, because the same bytes always land at the same address and different bytes are a different object. That property is worth more than it sounds.

## 10.3 Conflict handling (§23)

**No naive last-writer-wins for canonical knowledge.** Tracked states (`sync_state.state`): `LOCAL_ONLY` `REMOTE_ONLY` `SYNCED` `MODIFIED_LOCAL` `MODIFIED_REMOTE` `CONFLICT` `PENDING_UPLOAD` `PENDING_DOWNLOAD` `VALIDATING` `FAILED`.

Both sides modified → write a `conflict` row (status `OPEN`), keep **both** versions under the same object id, and surface it. Nothing is overwritten and nothing is chosen automatically. `secondbrain validate` reports open conflicts; `secondbrain health` flags them.

The `base_hash` column exists so a real three-way merge is possible rather than a two-way diff that cannot tell which side changed.

## 10.4 What must be true before sync is built

1. Server audit ingested — which host, how much space, what already runs there.
2. Backup verified **first** (§93). Sync failures propagate; without a proven restore, a sync bug is unrecoverable.
3. Evidence-plane transport chosen from measured volume (26.9 MB today; will grow past 6.78 GB once Downloads INCLUDE is ingested — that decides rsync vs object storage).
4. Class-E handling settled: prior context flagged live API keys pasted in plaintext during a debugging session. **Those need rotating regardless of sync**, and no key should reach the canonical store or Git at any point.
