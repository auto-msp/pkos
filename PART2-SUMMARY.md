# PKOS Part 2 — what was built, and what it measured

Session of 2026-09-11. Everything below is a measured number from a run, not
an estimate (SOW 43).

## The constraint that shaped the session

`device_bash` is still broken (the Plan9 mount error from the September 8
Windows update, now day 4), and this session's cloud container cannot reach
Perceptor on port 22 — the egress proxy blocks it. So §14.0–14.4 of the
handoff could not be *executed* from the session at all. What could be done
without a shell was code, tests, and the live Airtable connector. That is
what Part 2 is.

## 1. Ten new ingestion adapters — Phases 9, 10, 11, 12, 13, 15, 16, 17, 18, 19

Before this session `adapters/` held five modules and the store could ingest
four kinds of thing. Every remaining phase was described as "blocked on an
export only Moiz can request" — but **no adapter existed for any of them**, so
producing the export would not have helped.

| adapter | phase | reads |
|---|---|---|
| `takeout` | 10 (+ the Phase 7 unblock) | Google Takeout: Chrome history, bookmarks, Drive, Keep, Calendar, My Activity |
| `mbox` | 13 | email, mbox format |
| `notion` | 11 | Notion "Export all" zips |
| `github_stars` | 9 | `gh api user/starred` JSON |
| `chatgpt` | 15 | OpenAI `conversations.json` |
| `airtable` | 12 | connector snapshots |
| `instagram` / `facebook` | 17 / 18 | Meta "Download Your Information" |
| `linkedin` / `gumroad` | 19 / 16 | CSV exports |

Shared plumbing lives in `adapters/_archive.py`: content-keyed zip landing,
timestamp coercion, loud globs, Meta's encoding repair, CSV header detection,
and the URL/visit recorder.

**Takeout is chosen over the Drive connector deliberately.** The connector
returns a spreadsheet's *values*; Takeout exports the `.xlsx`, so formulas
survive. That was the stated Phase 10 blocker and it is now addressed.

**Takeout refuses to interpret mail.** It stores the `.mbox` bytes as evidence
and mints a `MailArchive` object marked `interpreted: false`, because Takeout
carries no trustworthy account identity and §14.5.5 flags mail as the one
corpus where that mistake is expensive to undo. The mbox adapter takes it from
there, with an explicit `--identity`.

## 2. Five real bugs found and fixed

Three were found by the tests written for the new code; two were pre-existing.

1. **Three adapters had no identity guard.** `notion`, `github-stars` and
   `airtable` each defaulted to a placeholder identity. Notion actually
   ingested two placeholder files under one before the test caught it. All ten
   identity-required adapters now raise rather than guess — and the test walks
   the registry, so a *future* adapter that forgets the guard fails here.

2. **`dr.create` could destroy the previous backup.** The backup directory is
   stamped to whole seconds and was claimed with `exist_ok=True`. Two backups
   in the same second meant the second one rewrote the first's JSONL mirror
   *before* failing on the database file. That is post-mortem 12.5 with a new
   trigger. Directories are now claimed atomically with a `-02` suffix on
   collision. The baseline suite had been passing on timing luck.

3. **The secret scanner missed self-hosted tokens.** Every pattern recognised a
   *vendor's* key format (`sk-ant-`, `ghp_`, `AKIA`, `AIza`). A bare 48-hex
   access token beside its own URL matched nothing — and one walked straight
   through a passing `no_secret_values_in_bodies` check during the Airtable
   ingest. Three high-precision patterns added. Deliberately *not* a general
   "long hex string" rule: this store is content-addressed, so 64-character hex
   strings are its evidence addresses, and such a rule would propose redacting
   the provenance chain itself.

4. **A bare git repo would have been ingested as thousands of binaries.**
   `EXCLUDE_DIRS` catches a directory named exactly `.git`. It does not catch
   `automsp-obsidian-vault.git`, which is the same thing under another name —
   and that folder is on the Phase 3 list. Bare repos are now detected by
   structure (`HEAD` + `objects/` + `refs/`) and refused with the `git clone`
   fix named.

5. **A text/plain stub could beat the real HTML body.** Much real mail is HTML
   with a "this message requires HTML" plain part. Preferring text/plain
   unconditionally stores the stub as the message forever. The adapter now
   picks by substance and records which part it used.

## 3. Phase 12 — real Airtable data, in the store

Measured across the live connector: **11 bases, 38 tables, 5 workspaces.**

- **Captured:** 7 tables, 125 records → ingested as **135 canonical objects,
  0 failures**, `validate` **PASSED**.
- **Measured but not captured:** 377 records (Companies 83, My Current
  Subscriptions 120, the Marvel/BOS hero trackers 152, TaskOps 6, Reels 1).
- **Measured empty:** the AutoMSP Financial Tracker. Revenue 0, Expenses 0,
  Clients 0. The tracker exists and has never been filled in.
- **Never probed:** 21 tables, all in the four Airtable project-template
  bases (two pairs of duplicates by name).

`90-evidence/airtable/airtable-estate.json` records all of that, so `gaps`
reports what Phase 12 still owes rather than implying the snapshots are the
whole of it.

Two columns were deliberately **not requested** from the API — `Login Username`
and `Banking Info` on *Startup Programs (Annual)*. Not requesting credential
material is stronger than requesting it and scrubbing afterwards.

## 4. Tests

**12 suites, all green** (9 existing + 3 new). The new ones assert the failures
that are silent in production: a Chrome timestamp read as epoch seconds dating
every URL to the year 54000; a Notion page renamed between exports duplicating
the workspace; a LinkedIn CSV re-sorted between exports duplicating every row;
Meta's double-encoded UTF-8; a ChatGPT tree read in dict order interleaving
abandoned branches into the transcript.

## 5. What still needs your machine

`99-runbooks/pkos-part2.ps1`, seven independent idempotent steps: convert the
four PuTTY keys · audit the four servers · Phase 3 folder ingest · ingest the
Airtable snapshots · ship the skeleton + bundle to Perceptor · **prove** the
offsite backup guard · reclaim the 380 MB.

Step 6 proves the guard and stops. Nothing in that file schedules anything —
no cron entry, no scheduled task, no pm2 schedule. That decision stays yours.
