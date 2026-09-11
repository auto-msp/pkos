# W3 — Google Drive Discovery Report (Moiz Contractor's PKOS)

**Status: PARTIAL / EMERGENCY PERSISTENCE PASS.** This worker was killed by a session rate-limit before any prior write attempt succeeded — the `pkos/` folder had zero W3 output on disk. This report and its companion evidence files were written from data already held in-context, without re-querying Google Drive, per an explicit priority override. Where the original four-task mission was not completed, that is stated plainly below rather than filled in with invented numbers.

Companion evidence files:
- `pkos/90-evidence/w3-gdrive-inventory.json` — 352 file/folder records retrieved, with per-category status and computed aggregates.
- `pkos/90-evidence/w3-gdrive-sheets-profile.json` — structural profile of 5 Google Sheets (Task C).

---

## Task A — Account / boundary discovery: COMPLETE

- **Resolved account:** `openmynewopportunities@gmail.com` (matches the session user's known email).
- **Accounts authorized to this connector:** 1.
- **Other Google accounts the user may own:** **UNDISCOVERED.** The connector exposes exactly one authorized account. This is a finding, not a verified absence — a separate authorization/connection would be required to check whether other accounts exist and what they hold.

## Task B — Corpus shape: PARTIAL

352 records were retrieved and are captured in `w3-gdrive-inventory.json`. **This is not the full Drive corpus** — every category below except three hit a `nextPageToken` on its very first page, meaning more records exist on Drive than were retrieved. No total file count for the account is known.

### Category completeness

| Category | Status | Retrieved | Total on Drive |
|---|---|---|---|
| Root-level folders (`parentId='root'`) | **COMPLETE** | 47 | 47 (re-queried at pageSize=100, identical set, no nextPageToken) |
| Google Slides | **COMPLETE** | 9 | 9 (same re-query method) |
| Google Forms | **COMPLETE** | 3 | 3 (same re-query method) |
| Google Sheets | PARTIAL | 108 | UNKNOWN (nextPageToken present after 3 pages) |
| Google Docs | PARTIAL | 50 | UNKNOWN (nextPageToken present after page 1) |
| PDF | PARTIAL | 5 | UNKNOWN (nextPageToken present; see pageSize note below) |
| .docx (uploaded Word) | PARTIAL | 50 | UNKNOWN |
| .xlsx (uploaded Excel) | PARTIAL | 50 | UNKNOWN |
| Images (image/png) | PARTIAL | 15 | UNKNOWN |
| Videos (video/mp4) | PARTIAL | 15 | UNKNOWN |
| **Total retrieved** | — | **352** | **UNKNOWN — not extrapolated** |

No grand total is estimated anywhere in this report. Every number above is an exact count of what was actually retrieved.

### Bytes

- **Total bytes summed across the 352 retrieved records: 204,712,478 bytes (≈195.3 MiB / ≈204.7 MB).**
- This is the sum of the Drive-reported `size` field for retrieved records only. It is **not** the size of the user's Drive — most of the corpus was never retrieved, so this number is a floor, not a total.

### mimeType breakdown (retrieved records only)

| mimeType | Count | Bytes |
|---|---:|---:|
| `application/vnd.google-apps.folder` | 47 | 0 |
| `application/vnd.google-apps.presentation` (Slides) | 9 | 69,090,506 |
| `application/vnd.google-apps.form` | 3 | 3,072 |
| `application/vnd.google-apps.spreadsheet` (Sheets) | 108 | 53,499,019 |
| `application/pdf` | 5 | 3,412,658 |
| `application/vnd.google-apps.document` (Docs) | 50 | 10,195,343 |
| `.docx` (wordprocessingml) | 50 | 2,732,902 |
| `.xlsx` (spreadsheetml) | 50 | 13,924,876 |
| `image/png` | 15 | 1,296,888 |
| `video/mp4` | 15 | 50,557,214 |

Google-native Docs/Sheets/Slides/Forms (170 records, 132.79 MB) are reported separately from uploaded binaries PDF/docx/xlsx/images/video (135 records, 71.92 MB) per the mission's requirement — see table above, split by mimeType.

### Age distribution (by `modifiedTime`, against 2026-09-07, computed over the 352 retrieved records only)

| Bucket | Count |
|---|---:|
| 0–6 months | 252 |
| 6–12 months | 52 |
| 1–2 years | 28 |
| 2–5 years | 20 |
| 5+ years | 0 |

This distribution is **skewed toward recent activity by construction** — most PARTIAL categories were sampled by Drive's default (recency-leaning) ordering on page 1, not a random or complete sample. It describes the 352 retrieved records, not the account's true age profile.

### Folder topology

47 top-level folders exist directly under My Drive root. Two are called out specifically as findings (full detail in `w3-gdrive-inventory.json` → `special_findings`):

1. **`AutoMSP BOS Claude Project`** (id `1WZC9iUZmtvoAdew9CWk5EPEneR4rpyVE`) is the Drive-side twin of the local device path `$HOME/mnt/AutoMSP BOS Claude Project` this worker was told to write evidence into — confirmed via byte-for-byte file-size matching and matching folder-creation timestamps between the Drive folder and the local synced copy. This means Drive Desktop sync will eventually pull this worker's own deliverables back into the Drive corpus being inventoried — outside this worker's control, but still compliant with the read-only-via-connector constraint because the write path is the local filesystem (via device tooling), never a Drive API write call.
2. A **`pkos` folder was already present on Drive** (synced) at the moment this worker began, created in the same minute as this discovery wave started. Reported as an observation, not acted upon.

Nested structure beyond the root level was not systematically mapped in this pass — `parentId` values are recorded per-file in the inventory JSON (e.g., a large cluster of files under parent `1TARn9u9meOpueCAf9cqrZqL_WSuN3y8L`, and the AutoMSP BOS Claude Project folder itself), but no separate folder-by-folder tree walk was completed.

### Shared vs. private / ownership breakdown — **NOT DELIVERED**

The mission asked for shared-with-others vs. private counts, and files owned by someone else. `owner != 'me'` and `sharedWithMe = true` queries were run earlier in the session, but their results were not transcribed into a retrievable file before the rate-limit interruption, and were not re-queried in this emergency pass (per explicit instruction not to re-query Drive). **This sub-requirement of Task B is incomplete.** Every record actually captured in the inventory JSON shows `owner: openmynewopportunities@gmail.com` and `shared: false`, but that reflects only the categories re-queried in the emergency pass (folders/Slides/Forms/Sheets/PDF/Docs/docx/xlsx/images/videos first pages), not a verified account-wide ownership/sharing census.

## Task C — Sheets as datasets: PARTIAL

Full detail in `w3-gdrive-sheets-profile.json`. Summary:

- 108 Google Sheets were retrieved (metadata only); **5 were opened** with `read_file_content` for structural profiling, chosen as largest/most-recently-modified/most business-critical by name. **103 were never opened.**
- **3 of the 5 reads succeeded:**
  - *Copy of HubSpot x MATG - Full-Stack AI Marketing Toolkit* (8.16 MB, largest Sheet in the sample) — a multi-tab AI-prompt/marketing-toolkit reference, not a numeric ledger.
  - *AutoMSP_Baseline_Capture_Worksheet* — 3-part structure (instructions / data capture / metric register). Contains a column explicitly labeled in-sheet as "calculated automatically, do not overwrite" that rendered as a plain value with **no formula text** — confirms `read_file_content` does not preserve formulas. 3 other same-titled copies exist and were not opened.
  - *My New Opportunities (Trello Dashboard)* — **title/content mismatch finding**: despite the name, actual content is dbohra.com-related data and a BNI (Business Network International) directory, not Trello data. Filenames in this corpus cannot be trusted as a content guide.
- **2 of the 5 reads failed** on tool-result size limits (see Task D) and are metadata-only in the profile: *botdirectory_bots* (best-size-match candidate, ID confidence noted as unverified) and *Financial Model - My New Opportunities* (same caveat).

**Mandatory statement, repeated per mission instructions: an AI-generated summary of a Sheet must never become the canonical financial or business record.** These profiles describe shape (tabs, columns, formatting cues), not values, and are explicitly not a substitute for the underlying Sheets.

**Canonicalization gap:** `read_file_content` returns computed values only, not formulas. A faithful ingestion pipeline needing live formulas requires the Sheets API (not loaded this wave) or an exported workbook, not this tool.

## Task D — Acquisition assessment

| Capability | Status | Evidence |
|---|---|---|
| Paging via `pageToken`/`nextPageToken` | VERIFIED, works | Used successfully across all 10 categories. |
| pageSize honored consistently | **VERIFIED INCONSISTENT** | PDF query at `pageSize=50` returned exactly 5 records, byte-identical, on two separate calls — with `nextPageToken` still present. Other categories (Docs/docx/xlsx/images/videos) honored their full requested page size on page 1. Root cause unconfirmed. |
| `search_files` result-size cap | VERIFIED | A `search_files` call hit a 54,140-character rendering limit and was diverted to an overflow file this session did not read back. Mitigation: smaller `pageSize`. |
| `read_file_content` result-size cap | VERIFIED | Two Sheet reads hit 134,487 and 335,926-character limits respectively (see Task C). |
| Formulas preserved on Sheet read | VERIFIED — **NOT preserved** | See AutoMSP_Baseline_Capture_Worksheet finding above. |
| `trashed` state queryable | VERIFIED — **NOT supported** | The `search_files` query grammar has no `trashed` operator; trashed status of any record is unverifiable through this tool. |
| Shared Drives (Team Drives) surfaced | **UNVERIFIED** | No query was run scoped to Shared Drives specifically this session. What test would settle it: a `search_files` query is not known to expose a Shared-Drive-scope parameter in this connector's grammar — would need to check for an undocumented parent/corpus term, or infer from whether any retrieved file's `parentId` resolves outside the user's My Drive tree. |
| Revision history access | **UNVERIFIED** | No revision-history tool was loaded this wave (out of the 4-tool scope given). Would need a dedicated revisions endpoint/tool to test. |
| Export Google Doc to portable format (e.g. PDF/docx) | **UNVERIFIED** | Not tested — the 4 loaded tools return natural-language content via `read_file_content`, not a format-preserving export; a real export capability was not probed. |
| Google Takeout as bulk-export path | **UNVERIFIED — not tested by this worker.** | Flagged only because it is the standard, widely-known Google account bulk-export mechanism; nothing in this session confirms it works for this account or connector context. |
| `download_file_content`, `get_file_permissions` | Out of scope this wave | These tools exist in the connector family (visible in the tool list) but were explicitly excluded from loading per mission scope — not tested, not loaded. |
| `create_file`/`update_file`/`copy_file`/`share_file`/`trash_file` | Out of scope this wave | Never loaded, never called — read-only constraint honored throughout. |

## LIMITATIONS

1. **This is an emergency re-persistence pass**, not the originally-planned full discovery run. The session was killed by a rate limit before any file was written to disk; this report and its companion JSON were reconstructed from in-context data only, with a hard budget of a few tool calls and an explicit instruction not to re-query Drive.
2. **No category total is a verified grand total.** 7 of 10 categories are first-page (or first-3-pages, for Sheets) samples only; every one of them still had a `nextPageToken` when sampling stopped. Total file count for the account is **UNKNOWN**, not estimated.
3. **Total bytes (204,712,478) covers only the 352 retrieved records**, not the account's actual storage usage, which is unknown and almost certainly much larger.
4. **Shared-vs-private and owner-not-me breakdown (explicitly requested in the mission) was not preserved and is not delivered** in this pass — see Task B above.
5. **Folder topology beyond the 47 root-level folders was not systematically mapped** — nested structure exists only implicitly via `parentId` values on individual file records.
6. **Sheets structural profiling covers 5 of 108 retrieved Sheets (and an unknown larger total)** — 103 retrieved Sheets have metadata only, and the true total Sheet count on the account is unknown.
7. **Two of the five Sheets profiles have unverified file-ID matches** (`botdirectory_bots` and `Financial Model - My New Opportunities`) because each has 2–4 near-identically-named copies in the corpus; the best size-matched candidate is reported, not a re-confirmed exact match, per the no-re-query constraint.
8. **`trashed` state is unverifiable** through the loaded tool's query grammar for any record in this inventory.
9. **Shared Drives visibility, revision history, Doc export fidelity, and Google Takeout are all UNVERIFIED** — no capability was invented or assumed; each is explicitly marked with what test would settle it.
10. **pageSize behavior is inconsistent and not fully explained** — any future ingestion pipeline built on this connector should not assume a requested page size will be honored, and should always check for `nextPageToken` regardless of how few records came back.
11. Byte totals and age-distribution figures are drawn from Drive-reported metadata as returned by the connector and were not independently cross-checked against the actual files.

---
*Generated by Discovery Worker W3. Read-only throughout — no Drive file was created, modified, copied, shared, or trashed by this worker.*
