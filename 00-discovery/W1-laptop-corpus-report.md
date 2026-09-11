# W1 — Laptop Corpus Discovery Report

**Worker:** DISCOVERY WORKER W1 (read-only)
**Device:** `moizsrtlap01` (Windows), reached via Linux VM mount
**Scan date:** 2026-09-07 (UTC)
**Scope:** the two mounted folders only — `C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project` and `C:\Users\MoizContractor\Downloads`
**Spec mapping:** §3 (existing corpus), §6 (Downloads ingestion), §7 (historical web pipeline), §18 (hashing), §19 (dedup), §75 (include/exclude)

> Every number below is **MEASURED** unless the line is explicitly tagged **ESTIMATE**.
> No file was modified, moved, renamed, deleted, or extracted. Archives were listed with `tar -tzf` only.

---

## 0. Headline verdict

| Question | Answer |
|---|---|
| Does the ~20,000-URL / 11-year history file exist in Downloads? | **NO — NOT FOUND.** |
| What is actually there? | **1,763 unique URLs** across 1,115 domains, spanning **8.1 years** (2018-07-02 → 2026-08-12) |
| Project corpus ("~2,000 files") | **526 files / 31,190,284 bytes (29.7 MiB)** — the "2,000 files" figure is not supported by the mounted folder |
| Downloads corpus | **57,145 files / 11,868,197,400 bytes (11.05 GiB) MEASURED**, plus 108 unmeasured dependency subtrees |
| Recoverable duplicate waste in Downloads | **670,063,736 bytes (0.67 GB)** across 1,037 confirmed groups |

---

## 1. Task A — Project folder audit (`AutoMSP BOS Claude Project`)

**MEASURED: 526 files, 248 directories, 31,190,284 bytes.** Every file carries a SHA-256 content hash (§18).
Full record: `pkos/90-evidence/w1-project-folder-inventory.json`

- Top level: 33 entries — 26 loose files (+3 more nested), 3 directories, 2 `.tar.gz` archives, 2 `.patch` files.
- Top-level files alone: **29 files / 8,389,738 bytes**. The remaining ~22.8 MB is almost entirely the `automsp-outreach-analytics` project's `node_modules` (Playwright).

### 1.1 Extension histogram (top 12, by count)

| Ext | Files | Bytes |
|---|---:|---:|
| *(none)* | 213 | 2,242,185 |
| `.js` | 89 | 14,608,500 |
| `.md` | 72 | 1,020,436 |
| `.sample` | 28 | 51,642 |
| `.html` | 13 | 1,399,882 |
| `.css` | 13 | 573,438 |
| `.sh` | 12 | 17,221 |
| `.txt` | 10 | 34,587 |
| `.json` | 9 | 48,324 |
| `.docx` | 8 | 688,882 |
| `.ts` | 8 | 2,365,369 |
| `.ps1` | 7 | 6,117 |

The knowledge-bearing content is the **~25 top-level `.md` / `.docx` / `.xlsx` / `.html` strategy documents** plus the **21-file `Throughline_Templates/` pack** (`T00`–`T20`). Everything else is application code.

### 1.2 Top 10 largest files

| Bytes | Path |
|---:|---|
| 6,142,930 | `automsp-outreach-analytics-live-data.tar.gz` |
| 3,425,603 | `automsp-outreach-analytics/node_modules/playwright-core/lib/coreBundle.js` |
| 3,239,355 | `automsp-outreach-analytics/node_modules/playwright-core/lib/utilsBundle.js` |
| 2,901,663 | `automsp-outreach-analytics/node_modules/playwright/lib/transform/babelBundle.js` |
| 1,110,840 | `automsp-outreach-analytics/node_modules/playwright-core/types/types.d.ts` |
| 823,302 | `automsp-outreach-analytics/node_modules/playwright-core/types/protocol.d.ts` |
| 685,808 | `automsp-outreach-analytics.tar.gz` |
| 643,184 | `.../playwright-core/lib/vite/traceViewer/assets/defaultSettingsView-B-dXF5JN.js` |
| 565,369 | `automsp-outreach-analytics/node_modules/playwright-core/lib/webp_codec.wasm` |
| 546,200 | `automsp-outreach-analytics/node_modules/playwright/lib/matchers/expect.js` |

### 1.3 Archives (listed, NOT extracted)

| Archive | Bytes | Entries | Files | Dirs |
|---|---:|---:|---:|---:|
| `automsp-outreach-analytics.tar.gz` | 685,808 | 169 | 145 | 24 |
| `automsp-outreach-analytics-live-data.tar.gz` | 6,142,930 | 529 | 481 | 48 |

Both wrap the same `automsp-outreach-analytics/` project root. The `live-data` archive is a **superset**: it adds `src/js/datasource.js` and a large live-data payload. Full entry lists and the set delta are in the inventory JSON under `archives`.

### 1.4 §19 Deduplication evidence — `automsp-outreach-analytics.stale-backup`

**VERDICT: `.stale-backup` is NOT a duplicate of `automsp-outreach-analytics`. It is an earlier, partial snapshot (a strict subset by content, with drift).**

Method: SHA-256 of every file in both trees, compared by relative path.

| Measure | Value |
|---|---:|
| Files in `automsp-outreach-analytics` | 367 |
| Files in `automsp-outreach-analytics.stale-backup` | 108 |
| Relative paths present in both | 107 |
| **Byte-identical (same SHA-256)** | **89 (82.4% of the backup)** |
| Content differs at same path | 18 |
| Present only in the backup | 1 (`.git/_stale_index.lock`) |
| Present only in the live tree | 260 (overwhelmingly `.git/objects/*`) |

The 18 drifted files are the real signal — 6 git-metadata files plus **12 source/build files**:
`build/build.js`, `build/verify.js`, `dist/artifact.html`, `dist/index.html`, `docker-compose.yml`, `src/index.html`, `src/js/app.js`, `src/js/charts.js`, `src/js/components.js`, `src/js/data.core.js`, `src/js/pages.analytics.js`, `src/js/pages.workspace.js`.

The lone `.git/_stale_index.lock` explains the folder's name: an interrupted git operation left a lock, and the tree was copied aside rather than repaired.

**Safe-to-collapse:** the 89 byte-identical files. **Do not blindly collapse** the 18 drifted files — they are a prior version worth diffing before discard.

### 1.5 Intra-folder duplicates (whole project folder)

**95 exact SHA-256 duplicate groups, 874,110 redundant bytes.** Small — mostly repeated `node_modules` licence and stub files. Not a cleanup priority.

---

## 2. Task B — Downloads corpus inventory

**Shape (MEASURED):** 139 top-level entries — **47 directories + 92 loose files**.
**Enumerated (MEASURED):** **57,145 files, 8,281 directories, 11,868,197,400 bytes (11.05 GiB).**
Full record: `pkos/90-evidence/w1-downloads-inventory.jsonl` (57,145 JSONL records, one per file, each carrying its §75 decision).

Coverage: **all 47 top-level directories and all 92 loose root files were walked to completion.** Dependency subtrees were deliberately pruned — see §2.4.

### 2.1 §75 classification — INCLUDE

**17,312 files / 6,775,034,801 bytes (6.31 GiB)** — 30.3% of files, 57.1% of measured bytes.

| Group | Files | Bytes |
|---|---:|---:|
| data (`.json .jsonl .xml .yaml .har`) | 8,883 | 538,249,324 |
| text (`.txt .md`) | 5,568 | 113,844,619 |
| web (`.html .htm .mhtml .url`) | 1,002 | 69,576,515 |
| doc (`.docx .doc .rtf .odt`) | 547 | 598,627,243 |
| image | 544 | 133,739,948 |
| media (`.mp4 .wav .mp3` …) | 271 | 1,462,968,296 |
| pdf | 198 | 508,285,290 |
| sheet (`.xlsx .csv .tsv`) | 146 | 163,269,597 |
| archive (`.zip .tar.gz` …) | 122 | 2,991,976,475 |
| slides (`.pptx .ppt`) | 25 | 163,050,874 |
| ebook | 2 | 31,354,012 |
| template (`.skill`) | 3 | 24,325 |
| contact (`.vcf`) | 1 | 68,283 |

### 2.2 §75 classification — EXCLUDE (counted, not deleted)

**39,833 files / 5,093,162,599 bytes (4.74 GiB).** Exclusion is a classification only; nothing was removed.

| Reason | Files | Bytes |
|---|---:|---:|
| repo / build / dev-cache path | 26,955 | 425,988,986 |
| source code / dev artifact (by extension) | 7,405 | 257,863,388 |
| unclassified, no extension | 4,447 | 566,686,522 |
| **installers (`.exe .msi .iso` …)** | **71** | **2,448,453,949** |
| `.mdc` (Cursor rules) | 173 | 2,998,617 |
| `.dot` (Graphviz) | 166 | 8,572,680 |
| `.download` (partial downloads) | 121 | 17,283,187 |
| `.pak` | 58 | 52,932,206 |
| fonts (`.ttf .woff .woff2`) | 49 | 16,205,764 |
| `.excalidraw` / `.excalidrawlib` | 31 | 31,430,454 |
| other long-tail extensions | 357 | ~4.7 M |

71 installers account for **2.45 GB — 20.6% of the entire measured corpus** for zero knowledge value. That is the single highest-yield exclusion.

**Review candidates:** the 4,447 extensionless files (566 MB) and the 166 `.dot` files include real content (Graphviz medical-record diagrams under `06 - Documents/GDrive Word Files/Medical - OpenEMR/`). These were auto-excluded by rule and deserve a human pass. The `.excalidraw` diagrams (31 MB) are arguably INCLUDE-worthy knowledge artifacts.

### 2.3 Age histogram (mtime, reference 2026-09-07)

| Band | Files | Bytes |
|---|---:|---:|
| 0–6 mo | 10,176 | 7,898,583,029 |
| 6–12 mo | 39,213 | 2,647,935,011 |
| 1–2 y | 7,553 | 161,673,932 |
| 2–5 y | 187 | 1,159,958,860 |
| 5 y+ | 16 | 46,568 |
| undated | 0 | — |

**Caveat:** these are Windows/NTFS mtimes surfaced through the mount. Bulk copies (e.g. the whole `06 - Documents/GDrive Word Files/` tree stamped `2026-06-21`) carry the copy date, not the authoring date. Age here measures **file custody, not content age**. Treat as a custody signal only.

### 2.4 Pruned dependency subtrees — the honest gap

To stay inside the tool timeout, 108 dependency subtree roots were identified but **not** walked file-by-file:

| Kind | Roots |
|---|---:|
| `__pycache__` | 40 |
| `.git` | 32 |
| `node_modules` | 28 |
| `.next` | 3 |
| `.venv` | 3 |
| `venv` | 1 |
| `.gradle` | 1 |

**One was measured in full** as a calibration exemplar:
`01 - AutoMSP & CoreIT/AutoMSP App/omnichannel-router/node_modules` = **16,356 files / 241,223,793 bytes**.

Measuring the remaining 107 was abandoned after both `os.walk` and `du -sb` each exceeded 60 s on a *single* `node_modules` — the mount is I/O-bound, not CPU-bound.

> **ESTIMATE (labelled, not measured):** if the 28 `node_modules` roots average even half the measured exemplar, they hold on the order of **~230,000 files / ~3.4 GB**, with the 32 `.git` roots adding more. **The true Downloads file count is therefore very likely 200,000–300,000, not 57,145.** Method: single-exemplar extrapolation across a same-kind population. Confidence: LOW. This number must not be reported as measured.
>
> **This does not affect the §75 INCLUDE set.** Everything unmeasured is `node_modules` / `.git` / `__pycache__` / `.venv` — categorically EXCLUDE. The 17,312-file / 6.31 GiB INCLUDE set is complete and fully measured.

### 2.5 Top 12 subtrees by bytes

| Bytes | Files | Subtree |
|---:|---:|---|
| 4,945,782,783 | 1,644 | `10 - Tools & Software` |
| 1,476,525,517 | 92 | *(loose root files)* |
| 1,020,287,701 | 2,782 | `06 - Documents` |
| 947,616,661 | 348 | `04 - Business & Clients` |
| 563,613,651 | 4,170 | `.tmp.driveupload` |
| 557,612,897 | 155 | `05 - Media` |
| 484,966,806 | 27,923 | `01 - AutoMSP & CoreIT` |
| 369,827,907 | 158 | `download` |
| 331,002,722 | 270 | `07 - Data & Exports` |
| 275,880,852 | 10,061 | `03 - AI Tools & N8N` |
| 130,742,867 | 486 | `Brain` |
| 123,435,001 | 11 | `ClaudeExport` |

`10 - Tools & Software` is 41.7% of all measured bytes and is almost entirely EXCLUDE (installers, ffmpeg binaries, a Debian qcow2 image, a QuickBooks installer).

### 2.6 Top 15 largest files

| Bytes | mtime | Path |
|---:|---|---|
| 629,637,120 | 2023-08-24 | `10 - Tools & Software/QuickBooks_Enterprise_Solutions_v23.0/.../QBooks/Data1.cab` |
| 454,737,964 | 2026-04-08 | `10 - Tools & Software/Zip Files/Complete Website Sitemap Replica.zip` |
| 340,066,304 | 2026-02-19 | `10 - Tools & Software/debian-12-genericcloud-arm64.qcow2` |
| 320,908,743 | 2026-07-13 | `Training.mp4` |
| 292,598,487 | 2026-08-22 | `Tellnova-1.1.11-win-x64.exe` |
| 271,640,021 | 2025-10-27 | `.tmp.driveupload/1691923` |
| 265,870,488 | 2026-08-21 | `GoogleDriveSetup.exe` |
| 234,842,314 | 2026-04-05 | `10 - Tools & Software/Zip Files/goose-1.29.1.zip` |
| 225,590,784 | 2026-04-30 | `.../ffmpeg-.../bin/ffplay.exe` |
| 224,073,216 | 2026-04-30 | `.../ffmpeg-.../bin/ffmpeg.exe` |
| 223,869,440 | 2026-04-30 | `.../ffmpeg-.../bin/ffprobe.exe` |
| 210,904,776 | 2026-01-09 | `10 - Tools & Software/Goose-win32-x64/dist-windows/Goose.exe` |
| 190,128,129 | 2026-05-02 | `04 - Business & Clients/Websites/Complete Website Sitemap Replica (4).zip` |
| 188,228,536 | 2026-05-24 | `07 - Data & Exports/Mach5 Data/TunnelBear-Installer.exe` |
| 170,220,205 | 2026-06-21 | `06 - Documents/GDrive Word Files/Company Documents/TMT (1).docx` |

### 2.7 Downloads duplicates (§19)

Method: group by exact byte size (files ≥ 20 KB, dependency dirs excluded), confirm with MD5 of first 256 KB + last 256 KB. 1,072 same-size groups covering 3,132 files were hashed — **zero skipped for time**.

**MEASURED: 1,037 confirmed duplicate groups, 670,063,736 bytes (0.67 GB) redundant.**
Full record: `pkos/90-evidence/w1-downloads-duplicates.json`

Largest offenders:

| Wasted | Copies | Representative path |
|---:|---:|---|
| 170,220,205 | ×2 | `TMT.docx` — `06 - Documents/GDrive Word Files/Company Documents/TMT (1).docx` vs `06 - Documents/Word files/TMT.docx` |
| 121,238,733 | ×2 | **`ClaudeExport/conversations.json` ≡ `raw_export/raw_export/conversations.json`** |
| 33,508,634 | ×3 | `template.zip` (2 sites + `10 - Tools & Software/Zip Files/Soliur Template.zip`) |
| 24,175,048 | ×2 | Instagram reel — `Instagram- Export/` vs `instagram-Export/` (same export, two spellings) |
| 17,759,090 | ×3 | `AutoMSP_DPIIT_Pitch_Deck_Narrated.pptx` (root, `06 - Documents/PPT Files/`, `files/`) |
| 15,677,006 | ×2 | *Measure What Matters* `.epub` in two folders |
| ~54 MB | ×2 each | 5 Twilio call recordings, each stored twice as `X.wav` and `X (1).wav` |
| 8,331,712 | ×3 | `ALL_unique_nodes.txt` (n8n node dump) in three folders |

**Pattern:** the waste is not random. It is (a) Google-Drive sync copies of `06 - Documents` colliding with local originals, (b) browser `(1)`/`(2)` re-download suffixes, and (c) the same export unpacked into two differently-cased folders. All three are mechanically detectable and safe to collapse on exact-hash match.

The `conversations.json` pair is the most important single finding for ingestion: **121 MB of Claude conversation export exists twice.** `Brain/Claude-Obsidian/conversations.json` (68,151,722 bytes, 2026-04-03) is a **different, older** export — verified distinct by head/tail MD5 — so there are two generations of Claude history, not three copies of one.

---

## 3. Task C — The 20,000-URL history file

### 3.1 VERDICT: **NOT FOUND**

There is **no file containing ~20,000 historical URLs** anywhere in the mounted Downloads folder. This is a measured negative, not a failure to look.

Full record: `pkos/90-evidence/w1-url-corpus-candidates.json`

### 3.2 What actually exists

**Union of every URL-bearing export found: 1,763 unique URLs across 1,115 unique domains — 8.8% of the claimed 20,000.**
Bookmark exports alone contribute **1,614 unique URLs**.

| Path | Bytes | mtime | Format | URL occurrences | Unique URLs | Domains | Date span |
|---|---:|---|---|---:|---:|---:|---|
| `HTML Files/Bookmarks - 12th Aug 2026.html` | 1,518,701 | 2026-08-12 | Netscape bookmark HTML | 1,654 | **1,466** | 1,112 | **2018-07-02 → 2026-08-12 (8.1 y)** |
| `HTML Files/bookmarks_organized (1).html` | 223,012 | 2026-08-12 | Netscape bookmark HTML | 1,466 | 1,466 | 1,112 | *(ADD_DATE stripped)* |
| `HTML Files/bookmarks_organized (2).html` | 214,304 | 2026-08-12 | Netscape bookmark HTML | 1,411 | 1,411 | 1,090 | *(ADD_DATE stripped)* |
| `02 - Code Projects/HTML Files/Latest Bookmarks From Company New Laptop.html` | 419,373 | 2025-12-07 | Netscape bookmark HTML | 492 | 309 | 223 | 2018-07-02 → 2022-07-05 (4.0 y) |
| `Text Files/unique_notion_urls.txt` | 11,425 | 2026-07-23 | plain text, 1 URL/line | 149 | 149 | 4 | — |
| `HTML Files/bookmarks_organized.html` | 11,322 | 2026-08-12 | Netscape bookmark HTML | 66 | 66 | 64 | 2024-01-08 → 2025-10-09 |

**Schema of the Netscape bookmark files:** `HREF`, `ADD_DATE` (Unix epoch), `LAST_MODIFIED`, `ICON` (base64 favicon), anchor text (page title), and an `<H3>` folder hierarchy — **182 folders** in the richest file. `ADD_DATE` is the usable temporal signal: 1,847 timestamps, earliest **2018-07-02**, latest **2026-08-12**.

The `bookmarks_organized*` files are **derived** from the master export — same 1,466 unique URLs, re-foldered into a curated taxonomy (`🤖 AI Tools & Models` → `Chat & LLMs` …) with `ADD_DATE` stripped. **Ingest the master for timestamps, the organized version for the human taxonomy.**

`Latest Bookmarks From Company New Laptop.html` is a **genuinely distinct, older** set (2018→2022) and contributes URLs absent from the 2026 export. It must be ingested separately, not deduped away.

### 3.3 URL-bearing datasets examined and ruled out

| Path | Size | Real rows | Why it is not browsing history |
|---|---:|---:|---|
| `07 - Data & Exports/Excel files/0.csv` | 114,833,937 | **1,393,753** | Instagram profile scraper. Schema: `username, name, bio, category, followerCount, followingCount, website, email, phone`. The `website` column is lead data. |
| `07 - Data & Exports/apollo-contacts-export.csv` | 11,120,828 | **5,851** | 66-column Apollo.io B2B export (incl. `Person Linkedin Url`, `Website`, `Company Linkedin Url`). CRM data. |
| `07 - Data & Exports/Excel files/all-contacts.csv` | 1,814,057 | **100,000** | HubSpot segment export. Schema: `Record ID, First Name, Last Name, Lead Status, Email, Phone Number, Job Title, Associated Company, LinkedIn URL, …`. |
| `openbot.coreitx.us.kg.har` | 32,412,297 | **662 entries / 348 unique URLs / 10 domains** | Single-session Chrome DevTools capture (`WebInspector 537.36`). One debugging session, not history. |
| `Text Files/06 - Code & Data Files/ALL_unique_nodes.txt` | 4,165,856 | 137,260 lines | n8n node-definition dump. |

### 3.4 What was searched (so the negative is auditable)

- Filename patterns across **all 57,145 enumerated paths**: `histor*`, `bookmark*`, `browsing*`, `visit*`, `places*`, `favorit*`, `url*`, `link*`, `export*`, `chrome*`, `edge*`, `firefox*`, `brave*`, `safari*`, `readwise`, `pocket`, `raindrop`, `omnivore`, `onetab`, `session buddy`, `toby`. → 198 non-dependency hits, all triaged above.
- `find -maxdepth 2 -iname` sweeps for the same patterns plus `*.sqlite*`, `*.db`, bare `History`, `Places*`. → **zero** browser-profile databases.
- Every `.sqlite`/`.db` in the corpus: **6 found**, all application databases — `03 - AI Tools & N8N/Cursor - N8N MCP/n8n-mcp/data/nodes.db` (62,623,744 B), `03 - AI Tools & N8N/OpenClaw Memory/gravity-claw.db` (4,096 B), and 4 zero-byte stubs. **None is browser history.**
- Size-band sweep: every `.csv/.json/.txt/.html/.jsonl/.tsv/.xml/.har/.md` between 500 KB and 40 MB outside dependency directories — 78 files, top 30 inspected by header and row count.
- Read-only SQLite inspection was prepared (`python3` stdlib, `file:…?mode=ro`) but **never needed — no browser database exists to open.**

### 3.5 Most likely explanation

The ~20,000-URL / 11-year corpus is **not in Downloads**. It almost certainly still lives in the **live browser profiles under `%LOCALAPPDATA%`** — Chrome/Edge `History` SQLite (`urls` and `visits` tables), which routinely hold 20k+ rows across a decade. The bookmark HTML exports in Downloads are a *curated subset* of that history (1,466 URLs), which is exactly the ratio one expects between bookmarks and full visit history.

**Recommended next step:** a separate folder grant for the browser profile directories (§4). Until then, §7's historical web pipeline can be seeded with the **1,763 measured URLs** but must not claim 20,000.

---

## 4. Task D — Browser profile and export evidence

**Found (exports only):** the 5 Netscape bookmark HTML files and 1 plain-text URL list catalogued in §3.2 — **1,614 unique bookmarked URLs**, evidence of at least two distinct browser profiles (a 2018–2022 "company laptop" set and a 2018–2026 current set).

Also present, adjacent but not browsing history:
- `09 - Social & Comms/instagram-Export/logged_information/link_history/link_history.html` (61,218 B) — Instagram in-app link history. **Parsed: contains 0 extractable `href` URLs** (Meta renders these as plain text, not anchors); a bespoke text parser would be required.
- `09 - Social & Comms/instagram-Export/…/stories_viewed.html` (1,577,718 B) and a full Instagram data-export tree — social activity, not web history.
- `09 - Social & Comms/user_data_export_2026-05-21…/conversations-20260521….json` (10,612,239 B) — a chat-platform export.

**GAP — live browser profiles are NOT reachable.** The mount exposes only `Downloads` and `AutoMSP BOS Claude Project`. `C:\Users\MoizContractor\AppData\Local\{Google\Chrome,Microsoft\Edge,BraveSoftware}\User Data\Default\` and `AppData\Roaming\Mozilla\Firefox\Profiles\` are outside the grant. **No attempt was made to reach them.** `get_device_info` confirms `AppData` exists in the home directory but it is not a connected folder.

---

## 5. LIMITATIONS

Everything W1 could not reach, and why.

1. **The 20,000-URL history file was not found.** This is a measured negative for the mounted scope. It is *not* proof the file does not exist on the laptop — only that it is not in `Downloads`.
2. **Live browser profiles (`AppData`) are unreachable.** Requires a separate folder grant for `%LOCALAPPDATA%\Google\Chrome\User Data`, `%LOCALAPPDATA%\Microsoft\Edge\User Data`, and `%APPDATA%\Mozilla\Firefox\Profiles`. **This is the single highest-value unblock for §7.** Note: a running browser holds a lock on `History`; it must be closed, or the file copied before reading.
3. **108 dependency subtrees were not enumerated file-by-file** (28 `node_modules`, 32 `.git`, 40 `__pycache__`, 3 `.next`, 4 `venv`/`.venv`, 1 `.gradle`). One was measured (16,356 files / 241,223,793 B). The rest are an **ESTIMATE** (§2.4) with LOW confidence. **The measured 57,145-file figure is a floor for the Downloads corpus, not a total.** No INCLUDE-classified content is affected.
4. **Other user folders were never in scope.** `get_device_info` shows `Documents`, `Desktop`, `OneDrive`, `Pictures`, `Videos`, `Recorded Calls`, `AutoMSP`, `bos-fable-5-work`, `automsp-obsidian-vault.git`, `open-claude-cowork` and ~90 more in the home directory. **None is mounted.** The "~2,000 existing files" in §3 of the spec is **not** the 526 files in `AutoMSP BOS Claude Project` — the remainder is presumably in these unmounted folders.
5. **Downloads duplicate detection used partial hashing** (first 256 KB + last 256 KB MD5) after exact size grouping, because full hashing of 11 GB over this mount is not feasible in the call budget. Collision risk is negligible for real files but this is **not** the full-SHA-256 rigour applied to Task A. The 670 MB figure is high-confidence, not cryptographically certain.
6. **Files < 20 KB and files inside dependency directories were excluded from Downloads duplicate detection.** Real duplicate waste is therefore ≥ 670 MB, never less.
7. **mtime measures custody, not authorship** (§2.3). Bulk-copied trees carry the copy date. The age histogram cannot be used to date content.
8. **Archive interiors were listed, not inspected.** `tar -tzf` gave entry names; contents were not read and nothing was extracted. The 122 `.zip`/`.tar.gz` files (2.99 GB) — including `ClaudeExport.zip` (24 MB), `download.zip` (100 MB) and three ~23 MB `automsp_pitch_chunks_part*of3.zip` — hold an **unmeasured** number of documents. **A second pass should list archive contents.**
9. **`sqlite3` CLI is absent from the VM.** Read-only inspection via `python3` stdlib was prepared and is viable; it was never exercised because no browser database was found.
10. **`0.csv` and `all-contacts.csv` row counts are line counts.** Both contain quoted multi-line fields (`bio`, address blocks), so true record counts are lower than 1,393,753 and 100,000 respectively. Line counts are reported as measured; **record counts require a real CSV parse.**
11. **No content was read beyond headers, first ~50 lines, and pattern counts.** File classification is by extension and path, not by content sniffing. Extensionless files (4,447 files / 566 MB) are therefore classified conservatively as EXCLUDE and **need a human or content-based pass**.
12. **Timing caveat:** two early walk passes over `01 - AutoMSP & CoreIT` were interrupted by the tool timeout and partially captured `node_modules` content before pruning was introduced. All records were de-duplicated by path before writing, so counts are correct, but the `01 - AutoMSP & CoreIT` file count (27,923) includes some dependency files that sibling subtrees pruned. This makes the EXCLUDE bucket slightly *more* complete for that one subtree — it does not inflate INCLUDE.

---

## 6. Evidence files produced

| File | Contents |
|---|---|
| `pkos/90-evidence/w1-project-folder-inventory.json` | 526 files with SHA-256, archive listings, `.stale-backup` comparison, extension histogram |
| `pkos/90-evidence/w1-downloads-inventory.jsonl` | 57,145 records: path, size, mtime UTC, ext, top-level subtree, §75 decision + group |
| `pkos/90-evidence/w1-url-corpus-candidates.json` | 6 URL-corpus candidates with real counts, schemas, date spans; the NOT-FOUND verdict; ruled-out datasets |
| `pkos/90-evidence/w1-downloads-duplicates.json` | 1,037 confirmed duplicate groups, 670,063,736 redundant bytes, method statement |
| `pkos/00-discovery/W1-laptop-corpus-report.md` | this report |

*Read-only throughout. Nothing outside `pkos/` was created, modified, moved, renamed, deleted, or extracted.*
