---
title: W2 - GitHub Evidence Discovery Report
worker: Discovery Worker W2
generated_at: 2026-09-07T04:44:44Z
status: PARTIALLY_COMPLETED (Task A only; Tasks B and C BLOCKED)
---

# W2 - GitHub Evidence Discovery Report

Maps to spec §76 (starred repos) and §44 item 18. Strictly read-only. No credentials were supplied, used, or requested by this worker.

## Headline result

- **Task A (identify account(s)):** RESOLVED, non-API evidence, single candidate found: **`mynewopportunities`**.
- **Task B (starred repositories, §76):** **BLOCKED — 0 records captured.** Not a rate-limit stop; a categorical proxy-level access block. See Limitations.
- **Task C (org repo inventory):** **BLOCKED — 0 records captured.** Same cause.
- **Rate limit:** Real budget observed was **15,000/hour** (core), not the 60/hour this worker was briefed to expect — see "Environment discrepancy" below. **14,993 remaining** is not the right framing; the correct number is **15,000/15,000 remaining, 0 used**, because every blocked call was rejected by the session proxy before it ever reached GitHub (confirmed — see evidence below).

---

## Environment discrepancy (read this first)

The task briefing stated: *"You have NO GitHub token. Use the UNAUTHENTICATED REST API. It is rate-limited to 60 requests/hour."* That is not what was observed. The very first call, `GET https://api.github.com/rate_limit`, returned:

```
X-Ratelimit-Limit: 15000
X-Ratelimit-Remaining: 15000
X-Oauth-Client-Id: Iv23liqTIFEtdIu6Vn1r
Github-Authentication-Token-Expiration: 2026-09-07 12:37:55 UTC
```

A 15,000/hour core limit and the presence of `X-Oauth-Client-Id` / `Github-Authentication-Token-Expiration` headers mean this session's outbound proxy is **transparently authenticating** every call to `api.github.com` with some credential this worker never supplied and cannot see — this is not a plain unauthenticated 60/hour connection.

However, that higher budget turned out to be irrelevant, because a **second, more restrictive layer** sits in front of it: the proxy only permits GitHub REST paths of the shape `repos/{owner}/{repo}/...` for repositories explicitly enabled for the session, and **zero repositories are enabled**. Every non-`/rate_limit` endpoint tried — user profile, org profile, org repo listing, starred repos, and four different individual `repos/{owner}/{repo}` paths (including one totally unrelated to AutoMSP, `octocat/Hello-World`, used as a control) — returned HTTP 403 from the proxy itself, never from GitHub:

| Endpoint tried | Result |
|---|---|
| `GET /rate_limit` | 200 OK — real GitHub data |
| `GET /users/mynewopportunities` | 403 — "sessions are bound to their configured repositories" |
| `GET /orgs/auto-msp` | 403 — same message |
| `GET /orgs/auto-msp/repos` | 403 — same message |
| `GET /users/mynewopportunities/starred` | 403 — same message |
| `GET /repos/auto-msp/automsp-platform` | 403 — "GitHub access to this repository is not enabled for this session. Use add_repo to request access." |
| `GET /repos/auto-msp/automsp-obsidian-vault` | 403 — same "not enabled" message |
| `GET /repos/mynewopportunities/automsp-outreach-analytics` | 403 — same "not enabled" message |
| `GET /repos/octocat/Hello-World` (control, unrelated repo) | 403 — same "not enabled" message |

**Proof these 403s never reached GitHub:** none of the seven 403 responses carried any `X-RateLimit-*` header (every genuine GitHub API response does, as the successful `/rate_limit` calls show). A second `GET /rate_limit` taken after all seven blocked attempts still read `used: 0, remaining: 15000` — byte-for-byte identical to the pre-attempt baseline. The proxy is intercepting and rejecting these calls before they leave the session's network boundary.

**Proof this is session-wide, not auto-msp-specific:** the `octocat/Hello-World` control call — a public repo with no relationship to this project — got the identical "not enabled for this session" 403 as the two AutoMSP repos. Zero repositories of any kind are currently enabled for this session's proxy.

I have no `add_repo`-equivalent tool in my toolset, and granting this session broader GitHub access is a permissions change outside a strictly-read-only discovery worker's mandate, so I did not attempt to search for or invoke one. Per my instructions ("if api.github.com starts failing, report the failure state — do not fall back to scraping HTML pages"), I stopped and am reporting the failure state here rather than working around it.

---

## Task A — Identify the account(s)

**Method actually used:** cheap non-API discovery only (per instructions, API was to be a last resort — and turned out to be unusable anyway per above).

### Candidate found: `mynewopportunities`

| Evidence | Source | Detail |
|---|---|---|
| Git remote origin URL | `automsp-outreach-analytics/.git/config` (device: moizsrtlap01, under `AutoMSP BOS Claude Project/`) | `[remote "origin"] url = https://github.com/mynewopportunities/automsp-outreach-analytics.git` |
| Same remote, backup copy | `automsp-outreach-analytics.stale-backup/.git/config` | identical origin URL |
| Repo-local git identity | same `.git/config` files | `[user] email = openmynewopportunities@gmail.com`, `name = AutoMSP` |
| Email match | cross-checked against this session's known user email | `openmynewopportunities@gmail.com` matches **exactly** — strong corroboration that this repo (and its GitHub remote) belongs to the account holder, not a third party |
| Commit authorship | `git log` on both repos (4 commits total: 3 in the live repo, 1 in the stale backup) | every commit authored by `AutoMSP <openmynewopportunities@gmail.com>` |
| README self-reference | `automsp-outreach-analytics/README.md` | contains the same `github.com/mynewopportunities/automsp-outreach-analytics.git` string |

**Not found / explicitly not present:**
- No global `git config --global user.email/name/github.user` was set on the device (all empty) — identity only exists at the per-repo level shown above.
- `package.json` in the repo lists `"author": "AutoMSP AI Automation Services"` (an org-style label, not a GitHub login) and `"repository": null` — no separate signal there.
- `.github/workflows/ci.yml` references only generic GitHub Actions (`actions/checkout`, `actions/setup-node`) and a Docker tag `automsp/outreach-analytics` — no other username.
- No `.netrc`, SSH config, or credential files were opened or searched (out of scope for a read-only identity check and unnecessary given the direct remote-URL evidence).

**Search for a second candidate (§45 — never assume one account):** I recursively scanned the entire mounted `AutoMSP BOS Claude Project` folder (excluding `node_modules`/`.git` internals) for any `github.com/<name>` pattern. Result: **exactly one** distinct username-shaped match anywhere in ~30 files — `mynewopportunities` (4 occurrences, all traced to the two sources above). One other match, `github.com/enterprise/startups` (3 occurrences), is GitHub's own marketing/pricing URL for its Enterprise-for-Startups program — **not a username**, and I am flagging it explicitly so it is not mistaken for one. I also checked `Downloads` (maxdepth 2) for any `.git` clones or repo remnants: none found (only Google Drive sync temp folders, `.tmp.driveupload`/`.tmp.drivedownload`).

**API verification: not possible.** `GET /users/mynewopportunities` was blocked at the proxy (see Environment discrepancy above) before it could confirm the account exists, return its profile, or surface any organization memberships. `GET /orgs/auto-msp` (for a public-members cross-check) was equally blocked.

**Verdict:** `mynewopportunities` is reported as the personal account with **high confidence from device-side evidence**, but **unverified against the live GitHub API**. Do not treat this as API-confirmed. No second personal-account candidate was found anywhere in the available evidence.

---

## Task B — Starred repositories (§76)

**Status: BLOCKED_NO_DATA. 0 of an unknown total captured.**

The `GET /users/mynewopportunities/starred?per_page=100` call (with `Accept: application/vnd.github.star+json` for `starred_at`, as instructed) was rejected by the session proxy with the same "sessions are bound to their configured repositories" 403 documented above — before a single page could be fetched. This is not a rate-limit exhaustion; the real budget (15,000/hour) was completely untouched. It is also worth being precise that `/users/{user}/starred` is not a `repos/{owner}/{repo}/...`-shaped path at all, so **no repo-enabling action could unlock it** even if one were available — it appears categorically out of scope for this proxy's allowlist design, not merely "not yet granted."

**Consequently, none of the following could be produced:**
- Any starred-repo record (full_name, html_url, owner, description, topics, language, stargazers_count, created_at, pushed_at, updated_at, archived, fork, license, homepage, size, open_issues_count, starred_at)
- Distribution by language
- Distribution by topic
- Distribution by year starred
- Cluster identification (AI/LLM, automation, infra, voice, data, etc.)
- Archived / stale (`pushed_at` >2 years old) flags for "disappearing knowledge" candidates (§64)

**I looked for a local substitute and explicitly did not use it as one:** the project folder contains `AutoMSP_Skills_Inventory_and_OSS_Landscape.md`, which ranks open-source projects by star/fork counts "pulled 2026-09-06." I read enough of it to confirm it is a **curated market-landscape research survey** ("for each capability a skill of that type requires, what are the leading open-source projects, ranked by stars and forks... a build landscape, not an attribution"), not a per-account personal starred-repos export with `starred_at` dates. Substituting it for Task B data would misrepresent both documents, so I did not.

`w2-github-stars.json` was still written, with `status: "BLOCKED_NO_DATA"`, an empty `star_records` array, and the full request/response evidence trail — so the blocker and its cause are on record even though there is no dataset to analyze.

---

## Task C — Org inventory

**Status: BLOCKED_NO_DATA. 0 of an unknown total captured.**

`GET /orgs/auto-msp/repos?per_page=100&type=all` was blocked the same way. I then tried the two repo names already known from prior context individually — `GET /repos/auto-msp/automsp-platform` and `GET /repos/auto-msp/automsp-obsidian-vault` — hoping the proxy's repo-scoped path might be permitted even though the org-level listing wasn't. Both returned a *different* 403: "GitHub access to this repository is not enabled for this session. Use add_repo to request access." I then ran a control call against an unrelated public repo (`octocat/Hello-World`) and got the identical message, proving **zero repositories of any kind are enabled for this session** — this is not specific to the auto-msp org.

**No repo metadata (visibility, language, size, created/pushed dates, default branch, topics, archived state) could be captured for any repository, including the two named in the task briefing.** Those two names are recorded in `w2-github-org-repos.json` under `context_only_unverified_repo_names`, explicitly labeled as unverified prior context, not fetched data — the org could contain more, fewer, or differently-configured repos than those two, and I have no way to check.

---

## Rate-limit status (final)

```
limit:     15000
used:      0
remaining: 15000
reset:     1788759741  (2026-09-07 ~06:42 UTC)
```

Zero of the real 15,000/hour budget was consumed this run — the constraint that stopped this task was never rate limiting, it was the repo-scope allowlist described above.

---

## LIMITATIONS

1. **Tasks B and C produced zero data**, not partial data. `w2-github-stars.json` and `w2-github-org-repos.json` both exist as required deliverables but contain empty result arrays with `status: "BLOCKED_NO_DATA"` and a full evidence trail of why. Do not read "file exists" as "task completed."
2. **Task A's identity is unverified against the live GitHub API.** It rests entirely on files found on the user's own machine (git remote config, matching commit-author email, README text). I could not call `GET /users/mynewopportunities` to confirm the account exists, is not suspended, or to see its public profile fields (bio, company, followers, etc.) — that call was blocked.
3. **This worker cannot determine whether `mynewopportunities` is the only personal GitHub account.** I can only report that no second candidate appears anywhere in the ~30 files I was able to search on the mounted device folders, and that the org-membership cross-check (`/orgs/auto-msp/members` or `/orgs/auto-msp` public-members) that might have surfaced additional linked accounts was blocked.
4. **The org repo count for `auto-msp` is completely unknown.** The two repo names in this worker's briefing (`automsp-platform`, `automsp-obsidian-vault`) are carried over as unverified context only — I did not independently confirm they exist, are correctly named, or are the complete list.
5. **The real cause of the block (a session-level repo-allowlist with zero repos enabled) is an environment/configuration fact, not something this worker can remediate.** No "add_repo" or equivalent capability exists in this worker's toolset, and requesting broader repo access would be a permissions change outside a strictly-read-only discovery worker's mandate — so none was attempted. If this dataset is needed, it requires either (a) a session with genuine unauthenticated network access to `api.github.com` that bypasses this proxy, or (b) a session where the relevant repos/users have been explicitly enabled via whatever mechanism the proxy's `add_repo` message refers to.
6. **README-body enrichment was never reached.** It was already planned as a deferred step even in the success case (to protect rate limit); it remains fully undone here since the base star-list it would enrich was never fetched.
7. **Deliverable files were written once, at the end**, rather than incrementally page-by-page as instructed for the rate-limit scenario — because zero pages were ever successfully fetched, there was no incremental progress to persist.
8. I did not attempt the GraphQL endpoint (`api.github.com/graphql`) as an alternate path; it shares the same host and proxy as the REST calls that were blocked, so it was judged highly likely to hit an identical restriction, and attempting it would not have changed the diagnosis already established by the `/rate_limit`-vs-everything-else pattern and the `octocat` control test.
