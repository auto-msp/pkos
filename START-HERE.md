# START HERE — what this is, where everything lives, what's next

Plain language. No jargon that isn't explained. Last updated 2026-09-08.

---

# PART 1 — What we are actually building

Think of a **library**.

| Library thing | Our name for it | What it really is |
|---|---|---|
| The archive room with the real books | **Evidence** | Exact copies of your actual files. Never edited, never deleted. |
| The card catalogue | **Canonical** | A database that says: what each thing is, where it came from, when, and what it relates to. |
| The search computer at the front desk | **Derived** | The search index. If it breaks, you rebuild it from the catalogue in under a minute. |

The whole point of the design: **the books and the catalogue are yours forever.** The search computer is disposable. If the software company disappears, or the database goes out of fashion, you still have the books and a plain-text catalogue.

---

# PART 2 — Where every file lives, right now

There are **three** places. That's it.

## Place 1 — Your original files (untouched)

```
C:\Users\MoizContractor\Downloads\
```

**Nothing here has been changed, moved, or deleted.** Not one file. Everything we did was read-only on your originals.

## Place 2 — The project folder (everything we built)

```
C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos\
```

Inside it, seven folders. Here is what each one is for:

```
pkos\
│
├── START-HERE.md            ← you are reading this
├── README.md                ← short version of this file
│
├── 00-discovery\            "WHAT DID WE FIND?"
│     Reports from the first pass. What files you have, what's on
│     GitHub, what's in Google Drive. Read these to understand your
│     own digital footprint.
│
├── 01-architecture\         "WHAT ARE WE BUILDING AND WHY?"
│     16 design documents. The rules of the system, the server audit
│     findings, and the plan. This is the thinking.
│
├── 02-canonical\            ★ THE ACTUAL SECOND BRAIN ★
│   └── pkos-store\             This is the valuable folder. 6 GB.
│       ├── evidence\blobs\     Copies of 9,035 of your files
│       ├── canonical\          The database + a plain-text copy of it
│       └── derived\            (empty here — see note below)
│
├── 03-skeleton\             "THE PROGRAM"
│     The `secondbrain` software. ~2,000 lines of Python. No
│     installation needed, no internet needed, no dependencies.
│
├── 90-evidence\             "THE RAW NOTES"
│     Machine-readable output from discovery. The server audits live
│     in 90-evidence\servers\.
│
└── 99-runbooks\             "SCRIPTS YOU RUN YOURSELF"
      The server audit script and its instructions. These are the
      ones you paste into PowerShell.
```

### If you only ever back up one folder, back up this one:

```
pkos\02-canonical\pkos-store\
```

That folder **is** the second brain. Everything else is either documentation about it, or the program that reads it.

## Place 3 — Your servers

**Right now: nothing.** The second brain exists only on your laptop. That is the single biggest risk in the whole system today, and Part 3 fixes it.

---

# PART 3 — What's inside the second brain right now

| Thing | Count |
|---|---:|
| Files copied in and catalogued | **16,516** |
| Your Claude conversations | **184** |
| Messages inside them | **15,908** |
| Documents you pasted into chats | **797** |
| Bookmarks (with their dates) | **1,448** |
| Server audits | 3 |
| **Total catalogued items** | **36,797** |
| Connections between items | **34,384** |
| Actual file copies stored | 9,035 blobs, **5.7 GB** |
| Duplicate files found and linked | 7,485 |

**What "connections" means.** For the first time the brain knows how things
*relate*, not just what exists: which message belongs to which conversation
(15,912 links), which message was a reply to which (15,733), and which
document was attached to which message (2,739). That web is what a knowledge
graph is built on — and it came out of your own chat history, not guesswork.

**Why 16,516 files but only 9,035 copies?** Because 7,481 of your files are *byte-for-byte identical* to another file. The system noticed and stored each unique thing once — but it still remembers all 16,516 names and locations. That saved 0.6 GB automatically.

**Nothing was deleted to achieve that.** Duplicates are *linked*, not removed. You can still find every copy.

---

# PART 4 — The one folder that isn't where you'd expect

`pkos\02-canonical\pkos-store\derived\` is **empty** (apart from a folder called `_unusable-on-this-mount` you can safely delete).

**Why:** the search index has to be a database file, and the way Claude connects to your laptop can't create new database files in that location. It's a permissions quirk, not a bug in your setup.

**Does it matter?** No. The search index is the "search computer at the front desk" — 100% rebuildable from the catalogue with one command, in 42 seconds. It currently gets built in a temporary spot each session. Once the brain moves to the server (Part 5), this stops being a consideration at all.

---

# PART 5 — DECISIONS MADE (2026-09-08) AND WHAT TO RUN NOW

## Decision 1 — the Second Brain goes on **rdp01 (132.145.133.39)**

**Not** MOIZ7TSVR01V. You ruled that machine out of the trust boundary, and that
decision stands regardless of its free space.

| Server | Free | Chosen? |
|---|---:|---|
| **rdp01 — 132.145.133.39** | **100 GB** | ✅ **yes** |
| rdp02 — Optimus Prime | 63 GB | no — carries the most open issues, and receives Megatron's nightly backup |
| MOIZ7TSVR01V | 211 GB | ❌ **excluded — outside trust boundary** |

rdp01 is also the healthiest machine in the fleet: 49% disk used, 12 containers
all running, no crash loops, Caddy owning ports 80/443 cleanly.

### ⚠️ Related finding you should act on separately

**Your Obsidian vault is already on the machine you just excluded.**
`/root/Obsidian/AutoMSP` on MOIZ7TSVR01V — 6.26 GB, plus a `vault-backup` dated
Sep 6, plus a Hermes install holding an `auth.json`. If that host is genuinely
outside your trust boundary, this matters considerably more than where the new
copy goes. It is a separate decision and this document does not resolve it.

## Decision 2 — cleanup scope: installers **and** all dependency folders

## Decision 3 — permanent deletion, not a staging folder

---

# STEP 1 — Free up the disk

**Run this. It takes a few minutes.**

```powershell
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos\99-runbooks"
.\Clean-Downloads.ps1
```

Want to see the list without deleting anything first? Add `-DryRun`.

**Why a PowerShell script instead of me doing it directly:** deletion through the
Claude ↔ laptop bridge is one network round-trip per file. A single `node_modules`
here holds **23,567 files** — about two minutes for one folder, and there are
roughly fifty. Natively on Windows it is a local operation and takes seconds each.
Same file list either way; this is purely about speed.

**What it removes:** 81 folders + 10 files.
- `node_modules`, `.venv`, `venv`, `.next`, `.nuxt`, `__pycache__`, `.gradle`, and friends
- QuickBooks (1,107 MB), ffmpeg full build (697 MB), Goose-win32-x64 (507 MB), InvisibleManXRay (170 MB)
- Loose installers: Tellnova, GoogleDriveSetup, TunnelBear, Telleport, node `.msi`, Hermes-Setup, emBridge, petdex, python-manager
- `debian-12-genericcloud-arm64.qcow2` (320 MB VM image)

**Already removed** by me before switching approach: `.tmp.driveupload` and
`.tmp.drivedownload` — Google Drive's stale upload cache, roughly 530 MB.

**What it never touches:** your 6,791 source files, every document, PDF,
spreadsheet, image and export, and the `AutoMSP BOS Claude Project` folder where
the Second Brain lives. Two guards re-check both rules at delete time, not just
when the list was built.

**This is permanent.** None of it is in the Second Brain — excluded files were
never copied into the evidence plane, which was the point of your §75 rule. All
of it is regenerable: `npm install`, `pip install -r requirements.txt`, or
re-download.

The script prints exactly how many GB it reclaimed when it finishes.

---

# STEP 2 — Move the Second Brain to rdp01

Do this after Step 1, so you are copying from a tidy disk.

**2a. Pack it into one file** — far faster than sending 9,035 separate files.

```powershell
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos\02-canonical"
tar -cf pkos-store.tar pkos-store
```

No compression on purpose: most of the content is already-compressed images,
video and zip files, so compressing would cost 20 minutes to save almost nothing.

**2b. Send it.**

```powershell
ssh root@132.145.133.39 "mkdir -p /root/pkos"
scp pkos-store.tar root@132.145.133.39:/root/pkos/
```

⏱️ 5.7 GB over your upload link. At 20 Mbps ≈ 40 min; at 50 Mbps ≈ 15 min.

**2c. Unpack and send the program too** (the program is only a few hundred KB).

```powershell
ssh root@132.145.133.39 "cd /root/pkos && tar -xf pkos-store.tar && du -sh pkos-store"

cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos"
tar -cf skeleton.tar 03-skeleton
scp skeleton.tar root@132.145.133.39:/root/pkos/
ssh root@132.145.133.39 "cd /root/pkos && tar -xf skeleton.tar"
```

**2d. Prove it works there.**

```powershell
ssh root@132.145.133.39 "cd /root/pkos/03-skeleton && PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=. python3 -m secondbrain validate"
```

`STATUS: PASSED` means the brain is alive on the server and arrived intact.

**2e. The check that actually matters** (~20 min — re-reads and re-fingerprints
all 9,035 files to prove not one byte changed in transit):

```powershell
ssh root@132.145.133.39 "cd /root/pkos/03-skeleton && PKOS_ROOT=/root/pkos/pkos-store PYTHONPATH=. python3 -m secondbrain validate --deep"
```

**2f. Build the search index on the server** — this is also the moment the
`derived` folder problem disappears, because a normal Linux filesystem has none
of the restrictions the Windows bridge imposes.

```powershell
ssh root@132.145.133.39 "cd /root/pkos/03-skeleton && PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=. python3 -m secondbrain rebuild-index && PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=. python3 -m secondbrain status"
```

## Why Step 2 matters

Your own spec (§21.1) says the **server** holds the master copy and the laptop is
a working copy. Right now that is backwards — everything exists in one folder on
one laptop. After Step 2 it is correct, and your laptop copy becomes the replica
it was always meant to be.

# PART 6 — The phases: done, next, later

Your original plan had 27 phases. Here they are honestly sorted.

## ✅ DONE

| Phase | What it means |
|---|---|
| **4 — Canonical storage** | The database and file-copy system exist and work |
| **5 — Provenance & versioning** | Every item records where it came from and every change is logged |
| **6 — Downloads ingestion** | 16,516 files catalogued, 0 failures |
| **8 — Bookmarks** | 1,448 URLs with their original save dates, back to 2018 |
| **14 — Claude history** | Every conversation you've had with Claude since March 2025, 0 failures |

## 🔶 PARTLY DONE — blocked on something specific

| Phase | Done | What's blocking it |
|---|---|---|
| **0 — Discovery** | most | Airtable never ran (we deferred it) |
| **1 — Server audit** | 3 of **6** | 4 servers still need their PuTTY keys converted |
| **3 — Your existing files** | only Downloads | ~90 folders on your laptop were never connected — `Documents`, `OneDrive`, `AutoMSP`, your Obsidian vault |
| **7 — Web history** | 1,448 of a hoped-for 20,000 | The real browser history is inside Chrome/Edge under `AppData`, which isn't shared with this session |
| **10 — Google** | 352 records | The connector doesn't preserve spreadsheet formulas, so it can't be the real route. Google Takeout is. |

## 🔜 NEXT — the three cheapest unlocks

These are minutes of your time and unlock days of work:

1. **Share more laptop folders.** Ask me and I'll request access to `Documents`, `OneDrive`, `AutoMSP`, and your Obsidian vault. → finishes Phase 3.
2. **Export your browser history.** Chrome → three-dot menu → Bookmarks and lists → Export. Or just share the `AppData` folder. → unlocks Phase 7 properly, the 20,000 URLs.
3. **Add an SSH key to adguard and automsp** through the Oracle Cloud web console. → finishes Phase 1.

## ⬜ NOT STARTED — grouped, so it's not a wall of 20 items

**Group A — Collect the rest of your stuff** (Phases 9–21)
GitHub Stars · Notion · Airtable · Gmail/Outlook/Zoho · Gumroad · Instagram/Facebook/LinkedIn · your ChatGPT and Claude exports.
**Good news:** your Claude conversation exports are *already sitting in Downloads* — 121 MB, plus an older 68 MB one. No export request needed, just a parser.
**Order matters:** for email, we must first answer "how many accounts?" — you have at least a personal Gmail and a corporate address. Mixing them up is one of the few mistakes that's genuinely expensive to undo.

**Group B — Make it smart** (Phases 22–23)
The knowledge graph (how things connect to each other) and better search (meaning-based, not just word-matching). Right now search matches words. This is what makes it answer *"what did I learn about X?"* instead of *"which files contain the word X?"*

**Group C — Make it safe** (Phases 25–26)
Laptop ↔ server sync, and proper backups. **Part 5 above is the first half of this.**

**Group D — Keep it alive** (Phases 24, 27)
The AI layer that reads your brain and answers questions, and the ongoing "what am I missing?" checks.

---

# PART 7 — The honest summary

**What's genuinely working:** 36,797 items catalogued with complete provenance, every one traceable back to the original bytes. All 10 integrity checks pass. Search now spans your files *and* your entire Claude history in one query. The program has no dependencies and will still run in ten years.

**The biggest risk today:** it still lives on one laptop. The 6.7 GB copy has now reached Perceptor (rdp01) — but until `validate --deep` runs there and passes, that copy is unproven, and an unproven backup is not a backup. Finishing Part 5 is still the single most valuable thing to do next.

**The biggest missing piece:** roughly 18,500 of your 20,000 URLs are still locked inside your browser, and your main document folders were never connected. Both are one permission away.
