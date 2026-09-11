# 14. Source Acquisition Matrix

**SOW §101 · Every "UNVERIFIED" is a capability nobody has tested. Nothing here is assumed (§107).**

| # | Source | Accounts | Acquisition method | Auth | Raw form | Canonical form | Incremental | Privacy | License | Cx | State |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Laptop project folder | 1 device | **filesystem adapter (built)** | local fs | files | File | hash+mtime | PRIVATE | MY_CONTENT | L | **COMPLETED** (150) |
| 2 | Laptop Downloads | 1 device | filesystem adapter | local fs | files | File | hash+mtime | PRIVATE | mixed | M | **READY** (17,312 INCLUDE) |
| 3 | Laptop other home folders | 1 device | filesystem adapter | local fs | files | File | hash+mtime | PRIVATE | MY_CONTENT | L | **BLOCKED** — folder grant |
| 4 | Browser bookmarks (Aug-2026) | 1 | **bookmarks adapter (built)** | none | Netscape HTML | Bookmark+URL+Visit | source hash | PRIVATE | THIRD_PARTY | L | **COMPLETED** (1,448) |
| 5 | Bookmarks (2018-22, 2nd machine) | 1 | same adapter | none | Netscape HTML | same | source hash | PRIVATE | THIRD_PARTY | L | **READY** — ingest separately |
| 6 | Chrome/Edge history | ? | SQLite read (`mode=ro`) | local fs | `History` db | BrowserHistoryEvent | last-visit ts | PRIVATE | MY_CONTENT | M | **BLOCKED** — `AppData` grant |
| 7 | Firefox bookmarks/history | ? | `places.sqlite` | local fs | SQLite | same | last-visit ts | PRIVATE | MY_CONTENT | M | **BLOCKED** — same |
| 8 | 5 OCI Ubuntu servers | ≥1 tenancy | **audit script (built, tested)** | human SSH | JSON | Source+workspace | per-run | SENSITIVE | MY_CONTENT | M | **BLOCKED** — no network path |
| 9 | Google Drive | **1 known, others UNDISCOVERED** | connector (partial) / **Takeout** | OAuth | files+metadata | File/Document | modifiedTime | PRIVATE | mixed | M | **PARTIAL** (352) |
| 10 | Google Docs | 1 | Takeout or Docs API | OAuth | doc export | Document | revision id | PRIVATE | MY_CONTENT | M | NOT_STARTED |
| 11 | Google Sheets | 1 | **Takeout / Sheets API — NOT the connector** | OAuth | xlsx/csv | Dataset+Worksheet | modifiedTime | PRIVATE | MY_CONTENT | H | **BLOCKED by design** — see note |
| 12 | Airtable | UNKNOWN | connector (live) | OAuth | bases/tables/records | Dataset+relations | modified ts | PRIVATE | MY_CONTENT | H | NOT_STARTED — deferred |
| 13 | GitHub Stars | 1 candidate, unverified | REST `/starred` + `star+json` | token | JSON | Repository | `starred_at` | PUBLIC | THIRD_PARTY | L | **BLOCKED** — proxy allowlist |
| 14 | GitHub org `auto-msp` | 1 | REST `/orgs/.../repos` | token | JSON | Repository | pushed_at | INTERNAL | MY_CONTENT | L | **BLOCKED** — same |
| 15 | Claude conversations | ? | **export already on disk** | none | `conversations.json` | Conversation+Message | export ts | SENSITIVE | MY_CONTENT | M | **READY** — 2 generations found |
| 16 | ChatGPT/OpenAI | ? | account export | login | zip/json | Conversation+Message | export ts | SENSITIVE | MY_CONTENT | M | NOT_STARTED |
| 17 | Gmail | **UNKNOWN — assume >1** | Takeout mbox / API | OAuth | mbox/raw | Email+Thread | history id | SENSITIVE | MY_CONTENT | H | NOT_STARTED |
| 18 | Outlook | UNKNOWN | Graph API / PST | OAuth | raw | Email+Thread | delta | SENSITIVE | MY_CONTENT | H | NOT_STARTED |
| 19 | Zoho | UNKNOWN | Zoho Mail API | OAuth | raw | Email+Thread | UNVERIFIED | SENSITIVE | MY_CONTENT | H | NOT_STARTED |
| 20 | Notion | UNKNOWN | export / API | token | md+csv / json | Document+Dataset | last_edited | PRIVATE | MY_CONTENT | M | NOT_STARTED |
| 21 | Gumroad | UNKNOWN | library export | login | files | Artifact | purchase ts | PRIVATE | **PURCHASED** | M | NOT_STARTED |
| 22 | Instagram | ≥1 | official data export | login | zip | Message/Image/WebPage | export ts | SENSITIVE | mixed | M | NOT_STARTED (an old scraper export exists on disk) |
| 23 | Facebook | UNKNOWN | official data export | login | zip | same | export ts | SENSITIVE | mixed | M | NOT_STARTED |
| 24 | LinkedIn | UNKNOWN | official data export | login | csv | Person/Org/Message | export ts | SENSITIVE | mixed | M | NOT_STARTED |
| 25 | Anthropic design env | UNKNOWN | **UNVERIFIED — no confirmed export** | — | — | — | — | SENSITIVE | MY_CONTENT | ? | NOT_STARTED |
| 26 | Vendor APIs from bookmarks | n/a | per-vendor | varies | varies | varies | varies | varies | THIRD_PARTY | H | NOT_STARTED |

**Cx** = complexity. L/M/H.

## Notes that change decisions

**#11 Google Sheets — the connector is disqualified.** Testing verified that **formulas are not preserved** when a Sheet is read through the connector. §79 requires formulas, precision, currency and worksheet structure to survive canonicalization, and forbids an AI-generated summary from becoming the canonical financial record. A connector read produces values without formulas — that is a lossy transform of exactly the thing that makes a spreadsheet a dataset. **Takeout or the Sheets API is required.** Also verified: result-size caps, pageSize inconsistency, and no `trashed` query operator.

**#13/#14 GitHub — retrying will not help.** The 403s come from the proxy's repo-scoped allowlist, not from GitHub, and `/users/{user}/starred` is not a repo-scoped path, so enabling repos would not reach it. This needs a different acquisition route entirely — a personal access token used outside this session, or a manual export.

**#15 Claude conversations — the evidence is already on disk.** Two `conversations.json` files (121 MB, present in two identical copies) plus an older 68 MB generation, all sitting in Downloads. Phase 14 needs no export request; it needs a parser. The two generations must be preserved as separate objects (§67: superseded, not deleted).

**#22 Instagram — the scraper export is not the official export.** The 114.8 MB `0.csv` found in Downloads is scraper output. §82 requires authorized export/API mechanisms; use the official data export, and treat the scraper file as third-party data of uncertain licensing.

**#17-19 Email — account discovery must come first.** Two identities are already visible (personal Gmail, corporate AutoMSP), and prior context references a third organisation. Ingesting mail under a merged account identity is one of the few errors here that is genuinely expensive to undo, because provenance would be wrong at the root (§46).

**#25 Anthropic design environment — no confirmed export mechanism.** Listed as UNVERIFIED rather than assumed available (§83, §107).
