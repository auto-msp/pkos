# 12. Historical Web Pipeline Architecture

**SOW §53–§64 · Status: `IMPLEMENTED` for bookmarks; `PARTIALLY_COMPLETED` overall**

## 12.1 The premise correction, first

| SOW claim | Measured |
|---|---|
| ~20,000 URLs | **1,448 unique / 1,654 events** (7.2% of the claim) |
| 11 years | **8.1 years** (2018-07-02 → 2026-08-12) |
| a file in Downloads | **no such file exists** |

Downloads was walked completely. No browser `History` or `places.sqlite` anywhere; the large CSVs are an Instagram scraper export and CRM exports, ruled out by real row counts.

**The missing ~18,500 URLs are almost certainly in the live Chrome/Edge profiles under `AppData`**, which is not mounted. Granting that folder is the single highest-value action for this phase.

§57 applies to the corpus itself: **a failure to find the file is not evidence the URLs never existed.**

## 12.2 Three objects, deliberately not collapsed (§58)

```
VISIT EVENT  →  URL  →  WEB SNAPSHOT
```

- **`url_visit`** — the temporal event: bookmarked at this time, in this folder, by this browser. **This is the research signal.**
- **`url`** — resource identity, canonicalized, with first/last seen and visit count.
- **`web_snapshot`** — retrieved content, if ever fetched. Carries `archive_provider` / `archive_url` / `attribution` so the system **never implies it archived a page it merely linked to** (§59).

Collapsing visits into URLs would destroy §60 and §62 — the frequency and temporal-clustering signals that make an eleven-year corpus worth more than a bookmark list.

## 12.3 URL canonicalization (§55) — implemented and deliberately conservative

Produces `original_url` / `normalized_url` / `canonical_url` **plus the exact rule list applied**, so every transformation is auditable.

Applied: lowercase scheme and host · IDNA encode · strip `www.` · drop default ports · strip `index.html`-class suffixes · strip trailing slash · **drop a known tracking-parameter allowlist** (48 params: utm_*, gclid, fbclid, msclkid, igshid, mc_*, …) · sort remaining params · drop fragments **except hashbang routes**, where the fragment is the resource identity · strip userinfo (it is a credential, §28).

**Two deliberate non-normalizations**, both required by "do not over-normalize in ways that change resource identity":
- **`http://` and `https://` stay distinct URLs.** They are different URLs. Variants are *linked* afterwards as `url`-kind duplicates (§19: canonical + alias) rather than merged — both identities and the evidence for the link survive.
- **Path case is never altered.** Many servers are case-sensitive.

Arbitrary query parameters are never dropped — only the known-tracking allowlist. Dropping an unknown param can change what resource you get.

`canonical_url` stays NULL until a real fetch resolves it (§56), rather than being guessed.

## 12.4 Validation, not coercion

11 of 1,665 entries were rejected as `INVALID_HOST` and routed to the dead-letter queue rather than being coerced into URLs. An earlier version of the canonicalizer accepted `"not a url at all"` by prepending `http://` — caught by a test, fixed. A host with spaces or no dot is not a URL, and manufacturing one would put fiction in the corpus.

## 12.5 Measured results

| Metric | Value |
|---|---|
| Anchors discovered | 1,665 |
| Acquired | 1,654 |
| Unique canonical URLs | **1,448** |
| Repeat URLs (dedup working) | 206 |
| Distinct registrable domains | **928** |
| Folders preserved | 182 |
| **ADD_DATE coverage** | **100%** |
| Rejected, isolated | 11 |

### Temporal profile (§62)

`2018:75 · 2019:180 · 2020:107 · 2021:4 · 2022:123 · 2023:281 · 2024:420 · 2025:367 · 2026:97`

**2021 is a near-total dormancy — 4 bookmarks in a year** — followed by sustained reactivation peaking in 2024. That is precisely the "dormant period → reactivation" pattern §62 asks for, visible in the first corpus ingested.

### Domain profile (§61)

`sap.com 53 · google.com 34 · youtube.com 29 · oracle.com 22 · apollo.io 17 · github.com 16 · zoho.com 13 · ondemand.com 12 · microsoft.com 10 · openai.com 8 · twilio.com 7 · linkedin.com 7`

SAP leads the next domain by 55%. That does not obviously match the AutoMSP positioning material sitting in the same folder, and is worth reconciling — it is the kind of §74 meta-knowledge signal the system exists to surface.

## 12.6 Not yet built

| Capability | SOW | State |
|---|---|---|
| Fetching URLs, redirect chains, snapshots | §56, §58 | `NOT_STARTED` — `fetch_status` defaults `NOT_FETCHED` on all 1,448 |
| Dead-link detection | §64 | needs fetching |
| Research trajectory linking (research→idea→decision→implementation) | §63 | needs Phase 22 graph |
| Second bookmarks file (309 URLs, 2018-2022) | — | **ingest separately; do not dedupe away** — different machine |
| Edge / Firefox exports | §44.14-15 | not provided |
| Browser history proper | §44.16 | **blocked on `AppData` grant** |

When fetching begins it needs rate limiting, `robots.txt` respect and §108 compliance — and §57 discipline: `NOT_FOUND` means the page is gone now, never that it never existed.
