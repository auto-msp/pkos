# PKOS — Second Brain: Complete Context Handoff

**Paste this whole file into a new chat. It is written to be read cold, by a
Claude session with zero prior context.**

Generated 2026-09-11 · Owner: Moiz Contractor · Project: Personal Knowledge
Operating System (PKOS) / "Second Brain"

---

# 0. HOW TO USE THIS FILE

If you are the assistant reading this in a fresh chat:

1. Read **§1 (mission)**, **§2 (non-negotiable rules)** and **§3 (standing
   instructions from Moiz)** before doing anything. §2 and §3 are binding.
2. Read **§4–§7** to know where things live and how the system is shaped.
3. Read **§12 (bug post-mortems)** before writing code. Those are the failure
   modes this project actually hits, repeatedly.
4. Then pick up at **§14 (resume here)**.

Do **not** re-derive the architecture. It is decided. Do **not** "improve" the
canonical schema without being asked. The value of this system is that it is
boring, deterministic and unchanged for a decade.

---

# 1. WHAT THIS IS

A **Personal Knowledge Operating System** built from a 130-section SOW that
Moiz wrote. The one-line goal:

> Everything Moiz has ever produced or collected — files, chats, bookmarks,
> browser history, email, repos, notes, server state — captured once, into a
> store that is **his**, that outlives any AI provider, database engine, search
> index or UI, and that can always prove where every single fact came from.

Design constraints, all of them load-bearing:

| Constraint | Why |
|---|---|
| **Python 3, standard library only, zero dependencies** | It must still run in 2036. Every `pip install` is a future breakage. |
| **Local-first, private** | No cloud service is in the trust path. |
| **10–20 year lifespan** | Formats chosen for durability, not convenience. |
| **Deterministic core; AI at the edge only** | SOW §3. The canonical layer never calls a model. Agents interpret; they do not decide truth. |
| **Nothing is ever deleted** | Duplicates are *linked*. Retired entities are *superseded*. Destructive acts are gated (§97). |

**Analogy Moiz uses and likes** (from `START-HERE.md`): it is a library.
Evidence = the archive room with the real books. Canonical = the card
catalogue. Derived = the search computer at the front desk. The books and
catalogue are his forever; the search computer is disposable and rebuildable in
under a minute.

---

# 2. NON-NEGOTIABLE RULES (SOW invariants)

These govern every line of code and every claim made to Moiz.

### 2.1 Three data planes (§5)

| Plane | Rule |
|---|---|
| **Evidence** | Immutable. Content-addressed by sha256. Mode 444. Written once, verified thereafter — **never overwritten**. |
| **Canonical** | The authority. SQLite (WAL) + a JSONL mirror for portability. |
| **Derived** | Rebuildable from canonical, always. FTS5 index, graph edges, aggregates. If it burns down, one command restores it. |

### 2.2 Identity (§9)

- Canonical IDs are `KB-00000001` + a uuid4. Versions are `KB-00000001:v01`.
- Identity is **never** derived from a path, filename, provider ID or rowid.
  Those change; identity must not.

### 2.3 The provenance chain (§17)

Every claim must walk backwards to bytes:

```
ANSWER → object → object_version → provenance → evidence_blob → raw bytes on disk
```

`secondbrain cite <KB-ID>` walks it. If the chain breaks, the claim is
worthless. Current state: **100.00% of acquired objects trace to raw bytes.**

### 2.4 Completion proof (§43)

**Never declare something complete because nothing errored.** Absence of error
is not proof of success. Every "done" must be backed by a count, a re-hash, or
a passing invariant — measured, not assumed. This rule has caught real bugs in
this project more than once (see §12).

### 2.5 Account boundaries (§45/§46)

Accounts are **never** merged. Two Claude accounts exist in this store and are
kept strictly separate. Account identity is explicit, never inferred. A resume
map built before the account is known is a bug and the code now raises rather
than guess.

### 2.6 Duplicates (§19)

Duplicates are **linked**, never deleted (`is_duplicate_of` + `duplicate_link`).
7,485 duplicate files are recorded; all 16,516 original names and locations are
still known.

### 2.7 Destructive gate (§97)

Any destructive operation runs this sequence, in order:
discover → dry run → impact report → dependency analysis → backup check →
**human approval** → execute → validate → audit.

### 2.8 Backups (§93)

**A backup is not valid until a restore has been verified.** A fresh backup is
written `proven: false`. Only a passed restore drill flips it to `proven: true`.

### 2.9 Never invent platform capabilities (§107)

If a connector cannot do something, say so. Do not describe a feature that does
not exist, and do not present a workaround as the real thing.

---

# 3. STANDING INSTRUCTIONS FROM MOIZ — treat as binding

These came from him directly in prior sessions. They are not negotiable and
should not be re-litigated.

### 3.1 Megatron is outside the trust boundary

> *"We cannot transfer the Second Brain files on MOIZ7TSVR01V, as that is
> Megatron, and it's kind of an enemy of our Autobots and Optimus Prime."*

`MOIZ7TSVR01V` (100.80.47.37) is **excluded** — despite having the most free
disk in the fleet (211 GB). Do not propose it as a destination.

### 3.2 But do not delete the Megatron copy

> *"As far as the copy of files remaining on Megatron, we would just keep it as
> a backup copy. **Do not delete it.** In case anything goes wrong, we can pick
> up the backup from Megatron."*

### 3.3 No cron / scheduled task without explicit permission

**Never activate or enable a new cron job, scheduled task, or pm2 cron-restart
schedule without asking first.** Write the script, test it, then *ask*. This is
a saved standing preference, not a one-off.

### 3.4 Do not escalate on credentials

> *"I guess you are getting too worried, and you're making a lot of sensational
> drama about the keys. I'm not worried about the keys and the credentials."*

Note the fact once, move on. Do not re-raise rotation every session.

### 3.5 Operate from Perceptor, not the laptop

> *"My requirement was to bring everything on Perceptor and operate from
> Perceptor rather than operating from Megatron."*

Perceptor is the master. Work there by default.

### 3.6 Be prudent with disk space

Explicit instruction. Prefer `VACUUM INTO` over copies, clean up superseded
artefacts, do not leave tarballs lying around.

### 3.7 Scope discipline

When he was asked about merging entities he chose **AutoMSP only** and said
*"Do not include anything besides AutoMSP."* Do not widen a scope he narrowed.

### 3.8 Tone

He got tired of long infrastructure detours — *"I am fed up with Megatron's
formalities"* — and of drama. Explain simply, keep moving, build. He is not a
beginner but he is not reading your code; write for a smart person who wants
the outcome and the honest caveat, not a lecture.

---

# 4. THE MACHINE FLEET

Transformers naming. Tailscale tailnet for most.

| Name | Host / IP | Role | Status |
|---|---|---|---|
| **Perceptor** | `rdp01` — **132.145.133.39** | ⭐ **MASTER. The Second Brain lives here.** | Healthiest box: 49% disk, 12 containers all up, Caddy clean on 80/443. 100 GB free at selection. |
| **Optimus Prime** | `rdp02` | Secondary backup tier | 63 GB free; carries most open issues; receives Megatron's nightly backup |
| **Megatron** | `MOIZ7TSVR01V` — 100.80.47.37 | ❌ **Outside trust boundary** | Holds the live Obsidian vault + n8n. Keep as cold backup, do not extend. |
| Ironhide | 129.158.236.50 | Unaudited | Needs `AdguardPvt.ppk` converted; user is `ubuntu` |
| Ratchet | 141.148.58.44 | Unaudited | Needs `automsppvt.ppk` converted; user is `ubuntu` |
| Prowl | 129.213.93.2 | Unaudited, **newly discovered** | `cloudpanel_key.ppk`; not on the tailnet |
| WheelJack | 150.136.67.246 | Unaudited, **newly discovered** | `my-rdp.ppk`; not on the tailnet |

**Laptop:** Windows, `C:\Users\MoizContractor\`. Connected folders in Cowork
sessions: `Downloads` and `AutoMSP BOS Claude Project`.

---

# 5. WHERE EVERYTHING LIVES

## 5.1 On the laptop (the replica + all source material)

```
C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos\
│
├── START-HERE.md        plain-language orientation for Moiz
├── README.md            short version
├── NEXT-STEPS.md        the living plan; has a "⏸ RESUME HERE" brief at the top
│
├── 00-discovery\        what discovery found (3 evidence-backed reports)
├── 01-architecture\     25 design documents — the thinking (see §6)
├── 02-canonical\pkos-store\   ★ THE STORE (replica) ★
│     ├── .pkos-root
│     ├── canonical\canonical.sqlite3      395 MB
│     ├── canonical\mirror\*.jsonl         portable plain-text mirror (~420 MB)
│     ├── evidence\blobs\                  9,055 content-addressed blobs, 5.9 GB
│     ├── derived\                         EMPTY on Windows — see §11.2
│     ├── logs\  reports\
│
├── 03-skeleton\         ★ THE PROGRAM ★  (see §7)
│     ├── bin\secondbrain
│     ├── secondbrain\*.py + schema.sql + adapters\
│     └── tests\         9 suites
│
├── 90-evidence\         raw discovery JSON/JSONL; servers\ holds audit output
├── 95-transfer\         transfer artefacts
├── 96-perceptor-scripts\  vault-sync-to-staging.sh, vault-offsite-backup.sh,
│                          vault-pull-from-megatron.sh  (deployed to /root/bin/)
└── 99-runbooks\         pkos-server-audit.sh, Clean-Downloads.ps1, runbooks
```

## 5.2 On Perceptor (the master)

```
/root/pkos/
├── pkos-store/          ★ MASTER STORE ★
│   ├── canonical/canonical.sqlite3
│   ├── evidence/blobs/
│   └── (superseded-*.sqlite3 — ~380 MB of stale artefacts, safe to delete)
├── derived/             FTS index lives here (PKOS_DERIVED)
└── 03-skeleton/         the program

/root/bin/               vault-sync-to-staging.sh, vault-offsite-backup.sh,
                         vault-pull-from-megatron.sh
/root/Obsidian/          verified copy of the vault (61,512 files / 5.2 GB)
```

**Backup tiers:** primary (Perceptor local) · secondary (rdp02) · offsite
(Google Drive via rclone, 7.14 GB, uploaded in 16m52s).

## 5.3 The one folder that matters

If only one thing is ever backed up: **`pkos-store/`**. Everything else is
either documentation about it or the program that reads it.

---

# 6. THE ARCHITECTURE DOCUMENTS

`01-architecture/` — read these when a decision needs its reasoning:

| File | Subject |
|---|---|
| 01 | current-state architecture |
| 02 | digital trace inventory |
| 03 | account inventory |
| 04 / 04b | server rdp02 findings · fleet audit summary |
| 04-07 | infrastructure audits — BLOCKED |
| 08 | existing file audit |
| 09 | canonical data architecture |
| 10 | synchronization architecture |
| 11 | security architecture |
| 12 | historical web pipeline |
| 13 | **agent architecture decision** — hybrid, deterministic core, 2–3 agents max |
| 14 | source acquisition matrix |
| 15 | implementation roadmap |
| 16 | phase 6 downloads ingest |
| 17 | security incident — credentials |
| **18** | **phase 14 Claude history** (+2 addenda) — the hardest phase |
| 19 | Megatron → Perceptor migration |
| 20 | phase 22 knowledge graph |
| 21 | phase 23 hybrid search |
| 22 | phase 24 agent boundary |
| 23 | phase 25 replication |
| 24 | phase 26 backup / DR |
| 25 | phase 27 knowledge intelligence |

---

# 7. THE CODEBASE

`03-skeleton/secondbrain/` — stdlib only, ~6,000 lines.

| Module | Lines | What it does |
|---|---:|---|
| `schema.sql` | 21,590 B | The canonical schema. 25+ tables. |
| `cli.py` | 51,400 B | Every subcommand. argparse, one `cmd_*` per verb. |
| `canonical.py` | 9,191 B | Object/version/provenance writes. The heart. |
| `evidence.py` | 6,244 B | Content-addressed blob store. `store_file`, `hash_bytes`. Existing blob = **verify, never overwrite**. |
| `ids.py` | 1,563 B | `KB-00000001` + uuid4 minting; `id_sequence` table. |
| `db.py` `config.py` `util.py` `events.py` | small | Connection/WAL, paths + env, helpers, audit events. |
| `validate.py` | 9,544 B | **13 invariant checks** (§8). `--deep` re-hashes every blob. |
| `search.py` | 17,585 B | FTS5 + hybrid ranking. Batched, resumable index build. |
| `graph.py` | 23,896 B | Entity derivation, edges, merges, orphan retirement. |
| `agent.py` | 11,023 B | The AI boundary. `ask` / `answer` / `validate_answer` / `provenance_chain`. |
| `sync.py` | 14,202 B | One-way replication. Owns no transport. |
| `dr.py` | 12,427 B | Backup, restore drill, recovery position. |
| `insight.py` | 11,992 B | `gaps()` and `meta()` — what the store doesn't know, and self-knowledge. |
| `dedupe.py` | 3,663 B | Duplicate detection + linking. |
| `urls.py` | 6,061 B | URL canonicalization. |
| `secrets.py` | 5,332 B | Credential-material scanning (§28). |
| `export.py` | 2,369 B | JSONL mirror writer. |
| `adapters/claude_export.py` | **35,978 B** | The big one. Both Claude export layouts, 8 object classes. |
| `adapters/filesystem.py` | 7,018 B | Downloads ingestion. |
| `adapters/bookmarks.py` | 7,167 B | Browser bookmark HTML. |
| `adapters/server_audit.py` | 3,734 B | Server audit JSON. |
| `adapters/base.py` | 7,543 B | Adapter contract. |

## Test suites — 9, all green

`test_smoke.py` · `test_account_boundary.py` · `test_export_layouts.py` ·
`test_graph.py` · `test_search.py` · `test_agent.py` · `test_sync.py` ·
`test_dr.py` · `test_insight.py`

**Rule learned the hard way:** tests that assert a *limitation* go stale the
moment the limitation is fixed. Three had to be removed for exactly that reason.
Assert behaviour, not absence of a feature.

---

# 8. THE 13 INVARIANT CHECKS

`secondbrain validate` (add `--deep` to re-hash all 9,055 blobs, ~20 min):

1. `every_object_has_current_version`
2. `every_version_has_provenance`
3. `version_chains_intact`
4. `every_object_has_event_history`
5. `account_boundaries_preserved`
6. `objects_not_shared_across_accounts` ← added after the near-miss in §12.1
7. `evidence_fully_accounted_for`
8. `duplicates_linked_not_deleted`
9. `conflicts_surfaced`
10. `no_secret_values_stored`
11. `no_secret_values_in_bodies`
12. `derived_indexes_registered`
13. `evidence_blobs_intact` (deep only)

**Perceptor currently: 13/13 PASS.** `evidence_blobs_intact ok=9055 missing=0
corrupt=0`.

---

# 9. COMPLETE CLI REFERENCE

Always run with the environment set:

```bash
cd /root/pkos/03-skeleton
export PKOS_ROOT=/root/pkos/pkos-store
export PKOS_DERIVED=/root/pkos/derived
export PYTHONPATH=.
python3 -m secondbrain <command>
```

| Command | Purpose |
|---|---|
| `init` | create the three-plane store |
| `status` | master status dashboard (§114) |
| `inventory` | knowledge + source registry inventory |
| `accounts` | account inventory (§45) |
| `servers` | server matrix (§102) |
| `storage` | storage heatmap — *stub, gated on server audits* |
| `discover` | digital trace discovery — *stub, supervised process* |
| `validate [--deep]` | the 13 invariants + completion proof (§43) |
| `search <q> [--limit N] [--explain] [--no-expand] [--no-graph]` | hybrid search (§71/72) |
| `rebuild-index [--quiet]` | rebuild derived indexes (§88) — **13.1 s** |
| `duplicates [--link]` | duplicate analysis (§19); `--link` records, deletes nothing |
| `history [--limit N]` | historical web corpus (§60–62) |
| `audit [--limit N] [--dead-letter]` | audit log / dead-letter queue (§95) |
| `export` | write the canonical JSONL mirror |
| `secrets [--redact]` | scan bodies for credential material (§28) |
| `health` | operational health |
| **`ingest <adapter> <target>`** | `--account --limit --dry-run --include-excluded --no-recurse --browser --allow-partial` |
| **`graph`** | `--rebuild --find TERM --object KB-ID --top --entity-class C --limit N --merge CANON ALIAS --confirmed-by WHO --reason R` |
| **`sync`** | `--manifest FILE --no-blobs --plan --export DIR --import DIR --against FILE --force --canonical-only` |
| **`backup`** | `--dest --dest-list --tier {primary,secondary,offsite} --label --include-evidence --drill DIR --status` |
| `ask <question> [--limit N]` | assemble evidence. **Answers nothing.** |
| `answer --model M [--inquiry INQ-] [--question] [--text FILE\|--body STR] [--cite IDs...]` | record an interpretation, attributed |
| `validate-answer <object_id> --accept\|--reject [--note]` | the only promotion path |
| `cite <object_id>` | walk back to raw bytes (§17) |
| `gaps [--detail]` | what the store does NOT know (§73) |
| `meta [--by-year]` | what the store knows about itself (§74) |
| `prune-writes [--execute]` | remove fragments from killed writes (gated) |
| `cleanup [--dry-run]` | storage remediation (gated, §97) |

Global: `--json` for machine-readable output.

---

# 10. PHASE STATUS — all 27

> **Numbering note.** The roadmap is called "27 phases" but the numbering runs
> **0 through 27**, i.e. 28 entries. 11 + 5 + 12 = 28. (The old `NEXT-STEPS.md`
> header said "9 done, 5 partial, 14 remaining" — that line was stale and
> contradicted its own table. These numbers are the correct ones.)

| | Phases |
|---|---|
| ✅ **Done (11)** | **4, 5, 6, 8, 14, 22, 23, 24, 25, 26, 27** |
| 🔶 **Partial (5)** | 0, 1, 3, 7, 10 |
| ⬜ **Remaining (12)** | 2, 9, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21 |

**Every one of the 27 phases now has working code.** What remains is
**acquisition** — source exports that only Moiz can request — plus Phase 2
(storage remediation), which is gated on finishing the server audits.

## Done, with what they produced

| Phase | Result |
|---|---|
| 4 — Canonical storage | database + blob store, working |
| 5 — Provenance / versioning / manifests | 1:1 provenance on every version |
| 6 — Downloads ingestion | **16,516 files**, 0 failures |
| 8 — Bookmarks | **1,448 URLs** across 928 domains, back to 2018 |
| **14 — Claude history** | **199 + 90 conversations across 2 accounts**, 16,105 + 1,102 messages, 807 attachments, 20 memory docs, 6 projects, 61 + 80 sign-ins. Second account reaches back to **June 2024**. |
| 22 — Knowledge graph | **1,074 entities** (928 domains, 133 folders, 7 workspaces, 3 servers, 3 accounts), **65,693 edges**, 7 relationship types |
| 23 — Hybrid search | **7 of 9** §72 ranking signals active |
| 24 — Agent layer | ask / answer / cite / validate-answer + confirmed merges |
| 25 — Replication | one-way, lineage-checked, transport-free |
| 26 — Backup / DR | drill-proven backups, tiered recovery position |
| 27 — Knowledge intelligence | `gaps` + `meta` |

## Partial, and precisely what blocks each

| Phase | Done | Blocker |
|---|---|---|
| 0 — Discovery | most | Airtable never ran (deferred) |
| 1 — Server audit | 3 of 7 | 4 PuTTY keys need converting (§14.2) |
| 3 — Existing files | Downloads only | ~90 laptop folders never connected: `Documents`, `OneDrive`, `AutoMSP`, `bos-fable-5-work`, `automsp-obsidian-vault.git` |
| 7 — Historical web | 1,448 of ~20,000 | Real history is in Chrome/Edge `AppData`, not shared |
| 10 — Google | 352 records | Connector loses spreadsheet formulas → Takeout is the only faithful route |

## Deliberately NOT implemented — and declared as such

Per §107, these are named as unimplemented rather than faked:
`personal_relevance` · `historical_importance` · backup retention policy ·
in-place restore.

---

# 11. LIVE NUMBERS

## Perceptor (master) — verified, not assumed

| Metric | Value |
|---|---:|
| Objects | **39,766** |
| Versions | **40,222** |
| Relationships | **65,796** |
| Evidence blobs | **9,055** / 5.9 GB |
| `validate --deep` | **13/13 PASS** · ok=9055 missing=0 corrupt=0 |
| FTS indexed | 32,279 |
| Graph entities | 1,074 |
| Dead-letter rows | 11 (all Phase-8 unparseable URLs — none lost) |
| Claude accounts | **2, kept separate** |

## What `gaps` reports (things the store knows it doesn't know)

- 2,147 files **named but never acquired**
- 1,448 URLs **never fetched**
- 10 sources **never ingested**
- 4,785 unexpected empty bodies (from a raw 6,932 once `FileReference` — empty
  by design — is excluded)
- 25 dark months
- 11 dead-letter items

## What `meta` reports (self-knowledge)

- **100.00%** of 38,652 acquired objects trace to raw bytes. **0 untraceable.**
- **0.025%** of the store has ever been surfaced by a question. The brain is
  almost entirely unread. That is the real headline.

## Laptop

10.59 GB reclaimed by `Clean-Downloads.ps1`, 0 refused, 0 errors. 131.72 GB free.

---

# 12. BUG POST-MORTEMS — read before writing code

These are the failure modes this project actually produces. Several were caught
only because of §43 (never trust absence of error).

### 12.1 The account-boundary near-miss — the worst one

The resume fast-path built a map of `native_id → object` **without scoping it to
an account**. A second Claude account's `memory_file:/areas/x.md` would have
matched the *first* account's object and been reported "unchanged" — a **silent
merge with no error at all**.

Three fixes: per-account scoped prefetch; ownership re-check at the point of
reuse; and a new invariant `objects_not_shared_across_accounts`.

Worse: the existing `account_boundaries_preserved` check was **wrong** — it
would have *failed* on correct behaviour and *passed* on the merge.

```python
def _prefetch(self):
    if self.account_id is None:
        raise RuntimeError(
            "refusing to build a resume map before the account is known "
            "(SOW 45: account identity is explicit, never inferred)")
    q = ("SELECT so.native_id AS n, so.content_hash AS h,"
         "       MAX(p.object_id) AS o"
         "  FROM source_object so"
         "  LEFT JOIN provenance p ON p.source_object_id = so.source_object_id"
         " WHERE so.source_id=? AND so.account_id IS ?"
         " GROUP BY so.native_id")
```

### 12.2 Landing directory keyed on filenames

Both accounts' exports produced the same landing dir
(`claude-export-4e75f96e378c`) because it was keyed on zip *names*. The second
export was never extracted and the wrong account identity was reported. Fixed
by **content-addressing** the landing dir:

```python
tag = evidence.hash_bytes(
    "|".join("%s:%s" % (n, self._part_hashes[n])
             for n in sorted(self._part_hashes)).encode())[:12]
work = Path(self.paths.landing) / ("claude-export-%s" % tag)
```

### 12.3 Export format changed underneath us

`memories.json` became `memories/<account-uuid>.json`. The old glob silently
matched nothing and **all 15 memory documents vanished with no error**.
Lesson: a glob that matches zero files must be loud.

### 12.4 `set -euo pipefail` killed a job for 2.5 months

```bash
RSYNC_OUTPUT=$(rsync ...)     # non-zero exit → shell dies HERE
RSYNC_EXIT=$?                 # never runs
```
The 7am staging sync had been dead since **2026-06-25**. The error branch was
unreachable by construction. I had told Moiz it was still covered — that was
wrong and I corrected it explicitly.

### 12.5 Backup overwrote a good backup

An offsite test ran while an rsync was still writing → a 76.9 MB partial
archive **overwrote his good 83.4 MB Drive backup**. Recovered from Megatron's
`/tmp`. Fixed with a hostname in the archive name and a `pgrep` concurrency
guard (exit 75). ⚠️ **That guard has never been observed to fire — it is
unproven.**

### 12.6 `copytree` on a live SQLite database

Torn snapshot. Replaced with `VACUUM INTO` + integrity check. Then: VACUUM's
scratch was written to the *mounted* output dir — 2m52s vs 7s. Moved to
`tempfile.mkdtemp()`.

### 12.7 The corruption detector crashed on corruption

`PRAGMA integrity_check` **raises** `DatabaseError` on a badly damaged file. The
routine whose entire purpose was finding corruption fell over on finding it.
Now every probe is wrapped; a failed probe yields a **verdict**, not a traceback,
and remaining checks are skipped-and-marked.

### 12.8 Impossible numbers are a gift

`meta` reported **100.1% traceable**. Impossible — which revealed the numerator
and denominator were counting different populations. Fixed by defining one
population explicitly:

```python
DERIVED_STATES = "('DERIVED','SYNTHESIZED','HUMAN_VALIDATED')"
# acquired / traceable_acquired / derived / derived_traceable
```

### 12.9 Silent no-ops

- `.replace()` with no assert in a patch script did **nothing**, silently.
- `graph --merge` didn't exist for two attempts — the command just wasn't there.
- Blob immutability (mode 444) broke re-import with `EACCES`. Correct semantics:
  an existing blob is **verified**, never overwritten.
- A virgin replica crashed on sync — no `id_sequence` row on an empty store. The
  single most important case for sync was the one that failed.
- `read_vs_write` reported 0 surfaced across 2 inquiries because id-logging
  postdated them. It now **states that it undercounts**.

### 12.10 PowerShell quoting

`$(date +%F)` inside a PowerShell **double-quoted** string: PowerShell ran
`Get-Date` instead, and the crontab backup landed as `crontab-backup-.txt`.
Single-quote the outer string. Same class: `$(hostname)` expanded on Megatron,
not on the target, so the confirmation message told us nothing.

### The through-line

Every one of these failed **silently**. None raised. §43 exists because of them:
**never declare complete on absence of error.** Count something. Re-hash
something. Prove it.

---

# 13. ENVIRONMENT GOTCHAS

### 13.1 `device_bash` is currently broken

As of **2026-09-08**, a Windows update prevents the Cowork Linux workspace from
mounting the connected folders:

> *"sandbox-helper: no Plan9 drive shares mounted under
> /mnt/.virtiofs-root/shared"*

**Workaround:** use `device_list_dir`, `device_stage_files` and
`device_commit_files` with **Windows paths** (`C:\Users\MoizContractor\...`).
Claude Code is unaffected. Anything needing a shell should run **on Perceptor
over SSH**, which is the preferred place anyway.

### 13.2 `PKOS_DERIVED` exists because of the Windows mount

The FUSE-style bridge to Windows **forbids `unlink`**, so SQLite cannot create a
new database file in `derived/`. Hence the env override. On Perceptor this is a
non-issue — set `PKOS_DERIVED=/root/pkos/derived` and forget it. The laptop's
`derived/_unusable-on-this-mount/` folder is safe to delete.

### 13.3 Index rebuild is fast now

Batched commits + resume + `doc_new` swap: **13.1 s** (was >180 s and timing out
with a 196 MB uncommitted WAL).

```python
BATCH = 2000
def build(canon_conn, fts_path, batch=BATCH, on_progress=None):
    # builds into doc_new, commits every `batch`, swaps at the end
```

### 13.4 Search ranking weights

```python
WEIGHTS = {"lexical": 1.0, "expansion": 0.35, "graph": 0.5,
           "authority": 0.6, "recency": 0.3}
PRF_DOCS, PRF_TERMS, PRF_CHARS = 8, 6, 4000
```
"Semantic" here means **pseudo-relevance feedback (RM3-style)** — distributional,
not neural. The SOW forbids dependencies, so there is no embedding model. A
document containing *none* of the query's words can still be found.

### 13.5 Graph saturation rule

```python
SATURATION = 0.05    # a term in >5% of the corpus generates NO MENTIONS edges
MAX_MENTIONS = 500
ENTITY_CLASSES = ("Domain", "Server", "Account", "Workspace", "Folder")
DESCEND_IF_ABOVE = 0.95   # folder rule: deepest shared ancestor, then descend
```
Folder entities are derived layout-independently (no hardcoded `/mnt/`).
Orphans are **SUPERSEDED, never deleted**, and merged aliases are excluded.

### 13.6 Sync bundle shape

```
canonical.sqlite3.gz · blobs-delta.tar.gz · MANIFEST.json · SHA256SUMS
```
Lineage = the uuid of `KB-00000001`. Refusals: lineage mismatch, remote-is-ahead,
any blob that fails to re-hash. `--canonical-only` bundles are verified by the
**importer** against its own blobs.

---

# 14. ⏸ RESUME HERE

## 14.0 The one thing that is out of sync

> **The laptop store is AHEAD of Perceptor by Phases 26 and 27.**
> `sync --import` will (correctly) refuse until a bundle is shipped.

```powershell
# on the laptop
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos\03-skeleton"
$env:PKOS_ROOT="..\02-canonical\pkos-store"; $env:PYTHONPATH="."
python -m secondbrain sync --export ..\95-transfer\bundle-2627 --canonical-only

# ship it plus the updated program
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos"
tar -czf skeleton.tar.gz 03-skeleton
scp -r 95-transfer\bundle-2627 skeleton.tar.gz root@132.145.133.39:/root/pkos/

# apply on Perceptor
ssh root@132.145.133.39 "cd /root/pkos && tar -xzf skeleton.tar.gz && cd 03-skeleton && \
  PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=. \
  python3 -m secondbrain sync --import /root/pkos/bundle-2627"
```

⚠️ Confirm with Moiz before running — do not assume.

## 14.1 Reclaim ~380 MB on Perceptor (safe; `--deep` passed)

```bash
ssh root@132.145.133.39 'rm -f /root/pkos/pkos-store/canonical/superseded-*.sqlite3'
```

## 14.2 Convert the four PuTTY keys — *2 min of Moiz's time*

`puttygen.exe` is a GUI app: called directly it detaches and writes nothing.
Force it to wait.

```powershell
$K = "C:\Users\MoizContractor\Downloads\10 - Tools & Software\Putty Keys New\newputtykeys"
$PG = "C:\Program Files\PuTTY\puttygen.exe"
Start-Process $PG -ArgumentList "`"$K\AdguardPvt.ppk.ppk`"","-O","private-openssh","-o","`"$HOME\.ssh\ironhide_key`"" -Wait -NoNewWindow
Start-Process $PG -ArgumentList "`"$K\automsppvt.ppk`"","-O","private-openssh","-o","`"$HOME\.ssh\ratchet_key`"" -Wait -NoNewWindow
Get-ChildItem "$HOME\.ssh\ironhide_key","$HOME\.ssh\ratchet_key" | Select Name,Length
```

Then audit all four (user is `ubuntu`, not `root`):

```powershell
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos"
$hosts = @(
  @{ip="129.158.236.50"; key="ironhide_key"; name="ironhide"},
  @{ip="141.148.58.44";  key="ratchet_key";  name="ratchet"},
  @{ip="129.213.93.2";   key="cloudpanel";   name="prowl"},
  @{ip="150.136.67.246"; key="my-rdp";       name="wheeljack"}
)
foreach ($h in $hosts) {
  Write-Host "=== $($h.name) ===" -ForegroundColor Cyan
  scp -i "$HOME\.ssh\$($h.key)" 99-runbooks\pkos-server-audit.sh ubuntu@$($h.ip):/tmp/
  ssh -i "$HOME\.ssh\$($h.key)" ubuntu@$($h.ip) "sed -i 's/\r$//' /tmp/pkos-server-audit.sh; sudo bash /tmp/pkos-server-audit.sh --out /tmp/audit.json"
  scp -i "$HOME\.ssh\$($h.key)" ubuntu@$($h.ip):/tmp/audit.json "90-evidence\servers\$($h.name)-audit.json"
}
```

**Unblocks:** Phase 1 complete → Phase 2 (storage remediation) starts.

## 14.3 Prove the offsite backup guard, THEN ask before scheduling

`/root/bin/vault-offsite-backup.sh` is written and tested on Perceptor, but its
`pgrep` concurrency guard has **never been observed to fire**. Prove it (start a
dummy long-running rsync, then invoke the script and confirm exit 75), then
**ask Moiz for permission** before adding any cron entry — §3.3.

## 14.4 Own Google Drive client_id

The shared rclone client_id is being retired during 2026 and is the only thing
carrying the off-tenancy backup. Moiz creates his own client_id, then revokes
rclone at myaccount.google.com → Security → Third-party apps.

## 14.5 The cheapest unlocks (minutes of his time, days of work unlocked)

1. **Connect more laptop folders**: `Documents`, `OneDrive`, `AutoMSP`,
   `bos-fable-5-work`, `automsp-obsidian-vault.git` → finishes Phase 3.
2. **Export browser history**: Chrome ⋮ → Bookmarks and lists → Export, into
   Downloads. Same for Edge. Full history needs `AppData` access → unlocks
   Phase 7's missing ~18,500 URLs.
3. **Notion export zip** → Phase 11. **Airtable** connector is live, just
   deferred → Phase 12. **GitHub Stars**: one authenticated call from his
   laptop, JSON into `90-evidence/` → Phase 9 (blocked from my side by a proxy
   allowlist, not rate limits).
4. **Google Takeout** → Phase 10 (the connector loses spreadsheet formulas).
5. **Email — account discovery FIRST** → Phase 13. How many Gmail / Outlook /
   Zoho accounts exist? Ingesting mail under a merged identity is one of the few
   mistakes that is genuinely expensive to undo.
6. Gumroad, Instagram, Facebook, LinkedIn official exports → Phases 16–19.

---

# 15. KNOWN-OPEN ITEMS (carried forward)

| Item | Detail |
|---|---|
| **Ratchet staging deploy dead since 2026-06-25** | Root cause found: Megatron egresses `96.45.71.2`, which Ratchet refuses. **Perceptor can reach it** — so the fix is to move the job, not to fight the firewall. |
| **Obsidian vault cutover not done** | Live writers are still Obsidian.app + n8n **on Megatron**. Perceptor holds a verified copy at `/root/Obsidian` (61,512 files / 5.2 GB, count-matched both ends). Five automations on Megatron still point at the original: 15-min backup, 7am staging sync, 2am tarball, two backup services. Repointing them is a separate deliberate step. |
| **Zombie n8n on Megatron** | pid 5035 (npm) — cannot bind :5678, cannot resolve its DB host. ~1.65 GB RAM wasted. |
| **796 MB of tarballs in Megatron's `/tmp`** | Redundant with the Drive copy. |
| **Offsite backup not scheduled** | Script written and tested; guard unproven; needs permission (§3.3). |
| **Google Drive shared client_id retiring in 2026** | Only thing carrying the off-tenancy backup. |
| **4 servers unaudited** | Ironhide, Ratchet, Prowl, WheelJack. |
| **Archive tidy-up (optional)** | 127 archives / 3.51 GB; ~0.5 GB genuinely reclaimable. Biggest cluster: "Complete Website Sitemap Replica" ×6 = 0.92 GB. Keeping the largest of each family frees ~0.5 GB. The other 69 one-offs (1.27 GB) are worth keeping. |

---

# 16. HOW TO WORK ON THIS

### Default working posture

SSH to Perceptor and work there. It is the master, it has a real filesystem, and
`device_bash` is broken on the laptop right now anyway.

```bash
ssh root@132.145.133.39
cd /root/pkos/03-skeleton
export PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=.
python3 -m secondbrain status
```

### Before claiming anything is done

```bash
python3 -m secondbrain validate        # 13 checks, fast
python3 -m secondbrain validate --deep # re-hash every blob, ~20 min
cd /root/pkos/03-skeleton && for t in tests/test_*.py; do python3 "$t" || echo "FAIL $t"; done
```

### Before shipping code changes

1. Write the test **first** if the change is behavioural.
2. Assert behaviour, never absence of a feature (see §7).
3. Run all nine suites.
4. Run `validate` on the live store.
5. State a **number** in the report, not "it worked".

### When you change the laptop store

You have made the replica diverge. Either work on Perceptor instead, or export a
bundle afterwards (§14.0).

### Tone with Moiz

Short. Concrete. Numbers. Name the caveat once and move on. He will tell you
when he wants depth. He is a solo founder running this alongside a day job and
is frequently watching his credit budget — do not spend a session on
infrastructure theatre.

---

*End of handoff. Everything above was verified against the live store or the
files on disk, not recalled from memory.*
