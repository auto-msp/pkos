# 1. Current-State Architecture Report

**Phase 0 · SOW §126 · Date: 2026-09-07 · Status: PARTIALLY_COMPLETED**

Everything below is measured or explicitly marked UNVERIFIED. No capability is asserted that was not tested (§107).

---

## 1.1 What was actually reachable

| Environment | Reachable | How verified |
|---|---|---|
| Cloud container (Linux, Python 3.11) | **yes** | direct |
| Laptop `moizsrtlap01` — connected folders | **yes** | `device_bash`, two mounts |
| Laptop — `Downloads` (11.05 GiB) | **yes** | granted mid-session |
| Laptop — rest of home (~90 folders) | **no** | not mounted |
| Laptop — browser profiles under `AppData` | **no** | not mounted |
| Google Drive | **yes, one account** | live connector |
| Airtable | connector live, **not executed** | deferred by you |
| GitHub API | **blocked** | see §1.3 |
| 5 OCI Ubuntu servers | **no** | see §1.2 |

## 1.2 The servers are unreachable from this session — measured, not assumed

| Probe | Result |
|---|---|
| container → `150.136.95.118:22` | blocked |
| container → `132.145.133.39:22` | blocked |
| container → `https://150.136.95.118` | proxy **403**, policy denial |
| container `ssh` binary | **not installed** |
| laptop VM → both IPs | `Network is unreachable` |
| laptop VM `tailscale` / `docker` / `oci` | **not installed** |

Tailscale runs on the Windows host; `device_bash` runs in an isolated Linux VM on that host with only the connected folders mounted and no route to the tailnet. There is no path from this session to the servers.

**Consequence:** SOW Phases 1, 2 and every deliverable that depends on server evidence (#4, #5, #6, and most of #7) are `BLOCKED`, not "pending". The unblock is mechanical and prepared: `pkos/99-runbooks/pkos-server-audit.sh`.

**Also unconfirmed:** the SOW says five servers. Two IPs appear in prior context. Prior notes also list three Linux nodes on the tailnet (`adguard`, `automsp`, `moiz7tsvr01v`) plus `rdp02`/"Optimus Prime" at `100.93.108.65` — sets that do not obviously reconcile to five. **The server inventory is itself an open question**, not a known list with missing detail.

## 1.3 GitHub is blocked by an infrastructure control, not by rate limits

The briefing assumed unauthenticated 60 req/hr. Reality: `GET /rate_limit` returns a **15,000/hr** budget with proxy-injected OAuth headers, but every other endpoint returns **403 directly from the proxy** — user profile, org profile, org repos, starred repos, and a neutral control repo (`octocat/Hello-World`). No `X-RateLimit-*` headers on any 403, and `used` stayed at 0, proving the calls never reached GitHub. The proxy enforces a **repo-scoped allowlist with zero repos enabled**.

`/users/{user}/starred` is not a repo-scoped path at all, so it is categorically unreachable — enabling repos would not fix it. **GitHub Stars (SOW §76, Phase 9) needs a different acquisition route**, not a retry.

One identity was recovered from device evidence alone: **`mynewopportunities`**, from `automsp-outreach-analytics/.git/config`, corroborated by commit-author email matching your known address. **API-unverified.**

## 1.4 The 20,000-URL claim does not survive contact with the evidence

This is the most consequential finding of Phase 0.

| Claim (§53) | Measured |
|---|---|
| ~20,000 URLs | **1,448 unique canonicalized URLs / 1,654 bookmark events** |
| 11 years | **8.1 years** (2018-07-02 → 2026-08-12) |
| file in Downloads | **no such file exists** |

Downloads was walked completely: 57,145 files, 8,281 directories, all 47 top-level dirs and 92 loose files. No browser `History` or `places.sqlite` anywhere. Candidates ruled out with real counts: a 114.8 MB `0.csv` (1,393,753 lines) is an **Instagram scraper export**; `apollo-contacts-export.csv` (5,851 rows) and `all-contacts.csv` are **CRM exports**; a 32 MB `.har` holds 662 entries / 348 URLs.

The richest real source is `Downloads/HTML Files/Bookmarks - 12th Aug 2026.html` — 1.5 MB, Netscape format, 182 folders, **ADD_DATE present on every entry**. A genuinely older second file exists (`02 - Code Projects/HTML Files/Latest Bookmarks From Company New Laptop.html`, 309 URLs, 2018→2022) and must be ingested **separately, not deduplicated away** — it is a different machine's history.

**Where the missing ~18,500 URLs almost certainly are: the live Chrome/Edge profiles under `AppData`, which are not mounted.** That is the single highest-value unblock for Phase 7.

## 1.5 What exists right now, running, on real data

`pkos/02-canonical/pkos-store/` — 45 MB, built this session, all invariants passing:

| Metric | Value |
|---|---|
| Canonical objects | **1,529** |
| Versions / provenance rows / events | **1,576 each** (1:1:1) |
| URLs / visits / domains | **1,448 / 1,654 / 928** |
| Files ingested | 81 knowledge + 69 classified-excluded |
| Evidence blobs | **74**, 26.9 MB, re-hash verified: 0 missing, 0 corrupt |
| Duplicates linked (not deleted) | 9 |
| Dead-letter items | 11 malformed URLs, isolated |
| Validation | **PASSED**, 0 failed checks |

## 1.6 Pre-existing knowledge infrastructure (partial)

From prior context, **UNVERIFIED this session** because the servers are unreachable: Hermes agent on desktop + `150.136.95.118` with a 15-skill pack and A2A live over Tailscale; an Obsidian vault synced to `auto-msp/automsp-obsidian-vault`; n8n, Postgres, Caddy, Qdrant-class services on `132.145.133.39`; root crontab entries including two "Apollo Prospecting Queue" jobs pointing at a **script that no longer exists on disk**.

That last item matters beyond tidiness: an unattended job once consumed an entire LLM subscription. The audit script surfaces every scheduled mechanism with its exact command line, which is why `scheduled` is a first-class section rather than a footnote.

## 1.7 Honest state summary

| Phase | State | Blocker |
|---|---|---|
| 0 discovery | `PARTIALLY_COMPLETED` | 3 of 5 workers killed by a rate limit; Airtable deferred |
| 1 server audit | `BLOCKED` | no network path; runbook prepared |
| 2 storage remediation | `BLOCKED` | depends on Phase 1 |
| 3 existing-file audit | `PARTIALLY_COMPLETED` | ~90 home folders unmounted |
| 4 canonical storage | **`COMPLETED`** | — |
| 5 provenance/versioning/manifests | **`COMPLETED`** | — |
| 6 Downloads ingestion | `READY` | inventory done; bulk ingest not run |
| 7 historical web | `PARTIALLY_COMPLETED` | 1,448 of a hoped-for 20k; browser profiles unmounted |
| 8 bookmarks | **`COMPLETED`** for the Aug-2026 export | second file + Edge/Firefox outstanding |
| 9 GitHub Stars | `BLOCKED` | proxy allowlist |
| 10 Google ecosystem | `PARTIALLY_COMPLETED` | 352 records, one account, paging incomplete |
| 12 Airtable | `NOT_STARTED` | deferred by you |
| 11, 13-21 | `NOT_STARTED` | phase-gated |
