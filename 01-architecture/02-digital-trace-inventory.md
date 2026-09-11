# 2. Digital Trace Inventory

**SOW §100, §109 · measured 2026-09-07**

## 2.1 Laptop `moizsrtlap01`

### Downloads — walked to completion

| Metric | Value |
|---|---|
| Files | **57,145** |
| Bytes | **11,868,197,400 (11.05 GiB)** |
| Directories | 8,281 |
| Coverage | all 47 top-level dirs + 92 loose files |

**SOW §75 classification** — exclusion is a label, never a deletion:

| Class | Files | Bytes |
|---|---:|---:|
| INCLUDE | **17,312** | 6,775,034,801 |
| EXCLUDE | **39,833** | 5,093,162,599 |

INCLUDE breakdown: data 8,883 · text 5,568 · web 1,002 · doc 547 · image 544 · media 271 · pdf 198 · sheet 146 · archive 122 · slides 25 · ebook 2 · template 3 · contact 1.

EXCLUDE is dominated by 26,955 repo/build files and 7,405 source files — plus **71 installers worth 2.45 GB, 20.6% of the entire corpus**. Installers are the single largest reclaimable category on the laptop and carry no knowledge value.

Age (mtime): 0-6mo 10,176 · 6-12mo 39,213 · 1-2y 7,553 · 2-5y 187 · 5y+ 16. The 6-12mo spike is bulk-copy custody, not authorship — many files were stamped 2026-06-21 by a Drive sync. **mtime is custody, not creation.**

### Duplicates in Downloads
**1,037 confirmed groups, 670,063,736 bytes (0.67 GB)**, zero groups skipped. Notable: `TMT.docx` ×2 (170 MB); `ClaudeExport/conversations.json` ≡ `raw_export/raw_export/conversations.json` (121,238,733 B each); `template.zip` ×3; an Instagram export stored under two differently-cased folder names; `AutoMSP_DPIIT_Pitch_Deck_Narrated.pptx` ×3; five Twilio `.wav` recordings each stored twice.

`Brain/Claude-Obsidian/conversations.json` (68 MB) is a **distinct older generation**, verified by head/tail MD5 — an earlier Claude export, not a duplicate. Preserve it: it is exactly the §67 "historical, superseded, still valuable" case.

**Method caveat:** dedup used size-grouping then first+last 256 KB MD5, not full SHA-256. High confidence, not cryptographic. Files under 20 KB and dependency dirs were excluded, so 670 MB is a **floor**.

### Project folder
526 files / 31,190,284 bytes including `node_modules`. Only ~29 top-level files (8,389,738 B) are knowledge content. **The SOW's "existing 2,000 files" is not supported here** — see deliverable #8.

`automsp-outreach-analytics.stale-backup` is **not** a duplicate: 108 files vs 367, 107 common paths, 89 byte-identical (82.4%), **18 drifted** (including `src/js/app.js`, `charts.js`, `data.core.js`, `dist/index.html`, `docker-compose.yml`), and one file only in the backup — `.git/_stale_index.lock`, which explains the name. Deleting it would lose 18 real divergences.

### Not reachable
~90 home folders were never mounted, including `Documents`, `Desktop`, `OneDrive`, `AutoMSP`, `bos-fable-5-work`, `automsp-obsidian-vault.git`, `Recorded Calls`, `Pictures`. **The "2,000 files" most likely live there.** Browser profiles under `AppData` are also unmounted — this is where the missing ~18,500 URLs almost certainly are.

**Unmeasured:** 108 dependency subtrees were not enumerated (28 `node_modules`, 32 `.git`, 40 `__pycache__`, 3 `.next`, 4 venv, 1 `.gradle`). One measured sample: 16,356 files / 241 MB. **ESTIMATE (low confidence): true Downloads file count is 200k-300k.** 57,145 is a floor. No INCLUDE content is affected — everything unmeasured is categorically EXCLUDE.

**Needs a human pass:** 4,447 extensionless files (566 MB), 166 `.dot`, 31 `.excalidraw` — auto-excluded by extension heuristic, possibly valuable.

## 2.2 Historical web corpus (canonicalized, in the store)

| Metric | Value |
|---|---|
| Unique URLs | **1,448** |
| Visit events | **1,654** |
| Distinct registrable domains | **928** |
| Span | 2018-07-02 → 2026-08-12 |
| Folders | 182 |
| ADD_DATE coverage | **100%** |
| Malformed, isolated | 11 |

**Per year — the §62 signal:** 2018:75 · 2019:180 · 2020:107 · **2021:4** · 2022:123 · 2023:281 · **2024:420** · 2025:367 · 2026:97.

2021 is a near-total dormancy (4 bookmarks in a year), followed by sustained reactivation peaking in 2024. That is a research-trajectory feature worth explaining, not noise.

**Top domains:** sap.com 53 · google.com 34 · youtube.com 29 · oracle.com 22 · apollo.io 17 · github.com 16 · zoho.com 13 · ondemand.com 12 · microsoft.com 10 · openai.com 8 · twilio.com 7 · linkedin.com 7.

SAP leading by 55% over the next domain is the strongest single signal in the corpus, and it does not obviously match the AutoMSP positioning material in the same folder. Worth reconciling.

## 2.3 Google Drive — one account, partial

Account: `openmynewopportunities@gmail.com`. **Other Google accounts are UNDISCOVERED, not absent** (§45).

352 records retrieved, 204,712,478 bytes — **a floor**: most categories returned a `nextPageToken`, so the account total is **UNKNOWN and was not extrapolated**.

Complete (verified exhaustive): root folders 47 · Slides 9 · Forms 3.
Partial: Sheets 108 · Docs 50 · .docx 50 · .xlsx 50 · PDF 5 · images 15 · video 15.
Age: 0-6mo 252 · 6-12mo 52 · 1-2y 28 · 2-5y 20.

**Verified connector limits:** pageSize inconsistency; result-size caps on `search_files`/`read_file_content`; **formulas are NOT preserved when reading a Sheet**; no `trashed` query operator. **UNVERIFIED:** Shared Drives visibility, revision history, Doc export fidelity, Google Takeout as the bulk path.

The formula finding is decisive for §79: **the connector cannot be the acquisition path for spreadsheets**. An AI-read Sheet loses exactly what makes it a dataset. Takeout or the Sheets API is required.

## 2.4 Everything else

| Source | State | Note |
|---|---|---|
| Airtable | `NOT_STARTED` | connector live; deferred |
| GitHub Stars | `BLOCKED` | proxy allowlist; not a rate limit |
| 5 OCI servers | `BLOCKED` | no network path |
| Notion, Gumroad, Gmail, Outlook, Zoho, Instagram, Facebook, LinkedIn, ChatGPT, Claude exports, Anthropic design | `NOT_STARTED` | phase-gated |

**Already on disk and unexploited:** two `conversations.json` Claude exports (121 MB current-generation ×2, 68 MB older generation) sitting in Downloads. Phase 14 has its raw evidence already — no export request needed.
