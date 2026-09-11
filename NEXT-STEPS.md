# NEXT STEPS — point by point

> 📄 **New chat? Read `PKOS-HANDOFF.md` in this folder instead.** It is the
> full cold-start context document — mission, binding rules, fleet map, code
> map, CLI reference, live numbers, bug post-mortems and the resume steps.
> This file remains the working plan.

# ⏸ RESUME HERE — 2026-09-08, 13:40 IST

**Perceptor (rdp01, 132.145.133.39) is the master and is fully current.**
Verified there, not assumed: 39,766 objects · 40,222 versions · 65,796
relationships · 9,055 blobs / 5.9 GB · **13/13 validate --deep PASS** ·
`evidence_blobs_intact ok=9055 missing=0 corrupt=0` · FTS 32,279 · graph 1,074
entities.

**The laptop is now a REPLICA.** If you work on the laptop store, it diverges
and the next `sync --import` will (correctly) refuse. Either work on Perceptor,
or re-export a bundle from the laptop afterwards.

## Phases: 11 done, 5 partial, 12 remaining  (numbering runs 0–27 = 28 entries)

| Done | 4, 5, 6, 8, 14, 22, 23, 24, 25, 26, 27 |
|---|---|
| Partial | 0, 1, 3, 7, 10 |
| Remaining | 2, 9, 11–13, 15–21 — **all acquisition, no building left** |

**All 27 phases now have working code.** What remains is acquisition — source
exports only Moiz can request — plus Phase 2 (storage remediation, gated on
finishing the server audits). Deliberately unimplemented and declared as such:
`personal_relevance`, `historical_importance`, backup retention, in-place
restore. Everything else is source ingestion, gated on
exports only Moiz can request.

## First three things next session

1. `ssh root@132.145.133.39 'rm -f /root/pkos/pkos-store/canonical/superseded-*.sqlite3'` — ~380 MB, safe now that --deep passed.
2. Off-site backup is still **not scheduled**. The script is written and tested
   on Perceptor (`/root/bin/vault-offsite-backup.sh`) but its concurrency guard
   has never been seen to fire. Prove the guard, then schedule.
3. Own Google Drive client_id — the shared one is being retired during 2026,
   and it is the only thing carrying your off-tenancy backup.

## Known-open, carried forward

- Ratchet staging deploy dead since **2026-06-25**; root cause found (Megatron
  egresses 96.45.71.2, Ratchet refuses it; **Perceptor can reach it**).
- Obsidian vault: live writers are still Obsidian.app + n8n **on Megatron**.
  Perceptor holds a verified copy at `/root/Obsidian`. Cutover not done.
- Megatron: a second n8n (pid 5035, npm) is dead weight — cannot bind :5678,
  cannot resolve its DB host. ~1.65 GB RAM.
- 796 MB of daily tarballs in Megatron's `/tmp`, redundant with Drive.

---


Updated 2026-09-08 (after Phase 14). **[YOU]** = a command you run.
**[ME]** = I do it, once it's unblocked.

---

## WHERE WE ARE

| Phase | State |
|---|---|
| 4 — Canonical storage | ✅ done |
| 5 — Provenance / versioning / manifests | ✅ done |
| 6 — Downloads ingestion | ✅ done — 16,516 files |
| 8 — Bookmarks | ✅ done — 1,448 URLs |
| **14 — Claude conversation history** | ✅ **done — 199 conversations, 16,105 messages, refreshed to 2026-09-08** |
| 1 — Server audit | 🔶 3 of **6** servers |
| 3 — Existing files | 🔶 Downloads only; ~90 folders never connected |
| 7 — Historical web | 🔶 1,448 of ~20,000 URLs |
| 10 — Google | 🔶 352 records; connector loses spreadsheet formulas |
| 0 — Discovery | 🔶 Airtable never ran |
| 9, 11–13, 15–21 | ⬜ not started |
| **22 — Knowledge graph** | ✅ **done — 1,074 entities, 65,693 edges** |
| **23 — Hybrid search** | ✅ **done — 7 of 9 ranking signals active** |
| **24 — Agent layer** | ✅ **done — ask/answer/cite/validate + confirmed merges** |
| **25 — Replication** | ✅ **done — one-way, verified, transport-free** |
| **26 — Backup / DR** | ✅ **done — drill-proven backups, tiered recovery position** |
| **27 — Knowledge intelligence** | ✅ **done — `gaps` and `meta`** |

**Store today:** 38,691 objects · 39,056 versions · 9,055 blobs / 5.7 GB ·
37,220 relationships · **11 / 11 validate checks pass** · **2 Claude accounts, separate** · 11 dead-letter rows
(all Phase-8 unparseable URLs, none lost).

**Laptop:** 10.59 GB reclaimed, 0 refused, 0 errors. 131.72 GB free.

---

# BLOCK 1 — UNBLOCKERS (each is minutes of your time)

### 1. [YOU] Convert the PuTTY keys — *2 min*
`puttygen.exe` is a GUI app: called directly it detaches and writes nothing.
Force it to wait.

```powershell
$K = "C:\Users\MoizContractor\Downloads\10 - Tools & Software\Putty Keys New\newputtykeys"
$PG = "C:\Program Files\PuTTY\puttygen.exe"
Start-Process $PG -ArgumentList "`"$K\AdguardPvt.ppk.ppk`"","-O","private-openssh","-o","`"$HOME\.ssh\ironhide_key`"" -Wait -NoNewWindow
Start-Process $PG -ArgumentList "`"$K\automsppvt.ppk`"","-O","private-openssh","-o","`"$HOME\.ssh\ratchet_key`"" -Wait -NoNewWindow
Get-ChildItem "$HOME\.ssh\ironhide_key","$HOME\.ssh\ratchet_key" | Select Name,Length
```

**Unblocks:** Ironhide + Ratchet audits. The user there is `ubuntu`, not `root`.

### 2. [YOU] Audit the four remaining servers — *~10 min each*
Two were blocked; **two we never knew existed** (Prowl, WheelJack — neither is
on your tailnet). Convert `cloudpanel_key.ppk` and `my-rdp.ppk` the same way.

```powershell
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos"
$hosts = @(
  @{ip="129.158.236.50"; key="ironhide_key";  name="ironhide"},
  @{ip="141.148.58.44";  key="ratchet_key";   name="ratchet"},
  @{ip="129.213.93.2";   key="cloudpanel";    name="prowl"},
  @{ip="150.136.67.246"; key="my-rdp";        name="wheeljack"}
)
foreach ($h in $hosts) {
  Write-Host "=== $($h.name) ===" -ForegroundColor Cyan
  scp -i "$HOME\.ssh\$($h.key)" 99-runbooks\pkos-server-audit.sh ubuntu@$($h.ip):/tmp/
  ssh -i "$HOME\.ssh\$($h.key)" ubuntu@$($h.ip) "sed -i 's/\r$//' /tmp/pkos-server-audit.sh; sudo bash /tmp/pkos-server-audit.sh --out /tmp/audit.json"
  scp -i "$HOME\.ssh\$($h.key)" ubuntu@$($h.ip):/tmp/audit.json "90-evidence\servers\$($h.name)-audit.json"
}
```

**Unblocks:** Phase 1 complete → Phase 2 (storage remediation) starts.

### 3. [YOU] Connect the rest of your laptop folders — *1 min, just say the word*
`Documents`, `OneDrive`, `AutoMSP`, `bos-fable-5-work`, `automsp-obsidian-vault.git`.
**Unblocks:** Phase 3 properly.

### 4. [YOU] Export browser history — *2 min*
Chrome → ⋮ → Bookmarks and lists → **Export bookmarks**, into Downloads. Same
for Edge. For full *history* (not just bookmarks) let me request `AppData`.
**Unblocks:** Phase 7 at real scale — the missing ~18,500 URLs.

---

# BLOCK 2 — MOVE THE BRAIN TO PERCEPTOR (rdp01, 132.145.133.39) — ✅ **DONE**

The server is the master (§21.1). `validate --deep` on Perceptor re-hashed all
9,055 blobs: **ok=9055 missing=0 corrupt=0**, 11/11 invariants pass, FTS index
rebuilt (31,206 objects in 39.7 s). The laptop is now the replica.

### 5. ✅ Vault: Megatron → Perceptor — **complete and verified**
**61,512 files / 5.2 GB on both ends — exact match.** (The earlier 399-file
reading was the rsync still in flight, not a partial copy.)

⚠️ **Copy only.** Five automations on Megatron still point at the original
(15-min backup, 7am staging sync, 2am tarball, both backup services).
Repointing them is a separate, deliberate step. Do not delete the original.

### 6. ✅ Second Brain: laptop → Perceptor — **done and proven**
The tar was taken while I was mid-ingest, so `canonical.sqlite3` inside it may
be a torn snapshot. The evidence blobs are unaffected — they are immutable and
content-addressed. A clean database made with SQLite's own backup API is
waiting at `pkos\02-canonical\pkos-store\canonical\canonical-snapshot.sqlite3`
(374 MB, `integrity_check: ok`, 0 foreign-key violations, 36,797 objects).

```powershell
ssh root@132.145.133.39 "cd /root/pkos && tar -xf pkos-store.tar && du -sh pkos-store"
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos\02-canonical\pkos-store\canonical"
scp canonical-snapshot.sqlite3 root@132.145.133.39:/root/pkos/
ssh root@132.145.133.39 "sha256sum /root/pkos/canonical-snapshot.sqlite3"
```
Must return **`641e0a0cb466f66b208f559c058e80b590092e26014c323f5720c364dcf42db0`**.
Then swap it in — the tar copy is moved aside, never deleted:
```powershell
ssh root@132.145.133.39 "cd /root/pkos/pkos-store/canonical && \
  mv canonical.sqlite3 canonical-from-tar.sqlite3 && \
  mv canonical.sqlite3-wal canonical-from-tar.sqlite3-wal 2>/dev/null; \
  mv canonical.sqlite3-shm canonical-from-tar.sqlite3-shm 2>/dev/null; \
  cp /root/pkos/canonical-snapshot.sqlite3 canonical.sqlite3 && ls -la"
```

### 7. [YOU] Ship the program and prove the copy — *~20 min, once*
```powershell
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos"
tar -cf skeleton.tar 03-skeleton
scp skeleton.tar root@132.145.133.39:/root/pkos/
ssh root@132.145.133.39 "cd /root/pkos && tar -xf skeleton.tar && cd 03-skeleton && \
  PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=. python3 -m secondbrain validate --deep && \
  PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=. python3 -m secondbrain rebuild-index"
```
`--deep` re-fingerprints all 9,035 blobs. That is the §93 proof that what
arrived is byte-for-byte what left. **Result:** §21.1 satisfied — the server
becomes the master, the laptop becomes the replica.

---

# BLOCK 3 — INGEST THE REMAINING SOURCES

### 8. ✅ [ME] Claude conversation history — **DONE, and now current to today**
199 conversations · 16,105 messages · 807 attachments · 20 assistant-memory
documents · 6 projects · **61 sign-in records**. Refreshed 2026-09-08 from the
new five-zip export format. Full detail — including why the "second account"
turned out to be the same account — in `01-architecture/18-phase14-claude-history.md`.

### 8b. ✅ [ME] Second Claude account — **DONE**
`openmynewopportunities@gmail.com` (`a34f2c68…`): 90 conversations, 1,102
messages, 80 sign-ins, back to **June 2024** — nine months earlier than the
other account reaches. Ingested with 0 unchanged, which is itself the proof
nothing was matched onto the first account's objects.

### 9. [ME] Notion export — you drop the zip, I parse it. *Phase 11*
### 10. [ME] Airtable — connector is live, only deferred. *Phase 12*
### 11. [YOU+ME] GitHub Stars — *Phase 9*
Blocked from my side by a proxy allowlist, not rate limits. One authenticated
call from your laptop, drop the JSON in `90-evidence/`.
### 12. [YOU+ME] Google Takeout — *Phase 10*
The connector loses spreadsheet formulas, so Takeout is the only faithful route.
### 13. [YOU] Email — **account discovery first** — *Phase 13*
How many Gmail / Outlook / Zoho accounts exist? Ingesting mail under a merged
identity is one of the few mistakes that is genuinely expensive to undo.
### 14. Gumroad, Instagram, Facebook, LinkedIn — official exports. *Phases 16–19*

---

# BLOCK 4 — MAKE IT INTELLIGENT

### 15. ✅ [ME] Knowledge graph — **DONE**
1,074 entities (928 domains, 133 folders, 7 workspaces, 3 servers, 3 accounts)
and 65,693 edges across 7 relationship types. Every entity derived from
structured evidence with the rule recorded in its provenance; the one text-based
edge type is fenced by a saturation rule. `secondbrain graph --rebuild`.
Detail in `01-architecture/20-phase22-knowledge-graph.md`.

### 16. ✅ [ME] Semantic + hybrid search — **DONE**
7 of 9 §72 signals active. Pseudo-relevance feedback (distributional, not
neural — the SOW forbids dependencies) plus graph-connectivity retrieval.
A document containing **none** of the query's words can now be found.
`--explain` shows every signal's contribution. `personal_relevance` and
`historical_importance` remain honestly NOT_IMPLEMENTED, with reasons.
Detail in `01-architecture/21-phase23-hybrid-search.md`.

### 17. ✅ [ME] Agent layer — **DONE**
`ask` assembles evidence and coverage gaps but writes no prose; `answer`
records a model's interpretation as SYNTHESIZED, attributed, requiring human
review; `cite` walks SOW 17 back to raw bytes; `validate-answer` is the only
thing that promotes it. Entity merges require `--confirmed-by`.
Detail in `01-architecture/22-phase24-agent-boundary.md`.
### 18. ✅ [ME] Laptop ↔ server replication — **DONE**
One-directional (server is master, SOW 21.1), owns no transport, and refuses on
lineage mismatch, wrong direction, or any blob that fails to re-hash.
`sync --manifest | --plan | --export | --import`.
Detail in `01-architecture/23-phase25-replication.md`.
### 19. ✅ [ME] Backup + DR — **DONE**
`backup --dest | --drill | --status`. A fresh backup is written `proven: false`;
only a passed restore drill flips it. Reports what restoring would LOSE, and
warns when a tier has never been tested or carries no evidence.
Detail in `01-architecture/24-phase26-backup-dr.md`.
### 20. ✅ [ME] Continuous knowledge intelligence — **DONE**
`secondbrain gaps` counts what the store does not know, each with the action
that closes it. `secondbrain meta` reports composition, provenance health
(**100.00% of acquired objects trace to raw bytes**) and read-vs-write —
0.025% of the store has ever been surfaced by a question.
Detail in `01-architecture/25-phase27-knowledge-intelligence.md`.

---

# OPTIONAL — archive tidy-up

127 archives / 3.51 GB, but only ~0.5 GB is worth reclaiming now that the
cleanup script has run. One real cluster:

| Family | Copies | Total |
|---|---:|---:|
| Complete Website Sitemap Replica | 6 | 0.92 GB |
| Website Sitemap and Linked | 3 | 0.18 GB |
| Complete Website Sitemap Creation | 3 | 0.16 GB |
| Chiropractor Website Project Layouts | 5 | 0.07 GB |
| Health and Fitness Gym | 7 | 0.04 GB |

Keeping the largest of each frees ~0.5 GB. Say the word and I generate the
script. The other 69 one-off archives (1.27 GB) are worth keeping.
