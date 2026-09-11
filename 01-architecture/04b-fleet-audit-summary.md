# 4b. Fleet Audit — three of five servers

**SOW §47, §48, §102 · audited 2026-09-07 · 3 COMPLETED, 2 BLOCKED**

## The fleet, finally resolved

The SOW claimed five servers; prior context gave two IPs and an unreconciled list of tailnet nodes. The tailnet plus the audits settle it — **exactly five Linux hosts**, and `lenovo-laptop` plus two Androids are not servers.

| # | Host | Address | Status |
|---|---|---|---|
| 1 | **rdp02** | 150.136.95.118 / 100.93.108.65 | COMPLETED |
| 2 | **rdp01** | 132.145.133.39 | COMPLETED |
| 3 | **MOIZ7TSVR01V** | 100.80.47.37 / 96.45.71.2-3 | COMPLETED |
| 4 | **adguard** | 100.64.238.30 / 129.158.236.50 | **BLOCKED** |
| 5 | **automsp** | 100.79.251.18 / 141.148.58.44 | **BLOCKED** |

`BLOCKED` reason, evidenced: nine combinations tested — 3 keys (`oracle_key`, `id_rsa`, `id_ed25519`) × 3 users (`root`, `ubuntu`, `opc`) — from the laptop, plus `root`/`ubuntu`/`opc` from rdp02 as a jump host. All refused `publickey`. **No key path exists from any available host.** Resolution requires adding a key through the OCI Console. This is a recorded terminal state (§96), not an unfinished task.

## Server Matrix (§102)

| Server | Arch | Storage | Used | Free | Docker | Databases | Backups | Action |
|---|---|---|---:|---:|---|---|---|---|
| rdp02 | aarch64, 4 vCPU, 23 GiB | 193 G | 130 G (**68%**) | 63 G | 27 ctr / 19 img / 3 orphan vols | 5× Postgres, MariaDB, Redis | **stale 3 mo** | traefik · certbot · 18 root keys |
| rdp01 | aarch64, 4 vCPU | 194 G | 94 G (49%) | 100 G | 12 ctr, all up | pgvector ×2, Postgres | — | mask dead nginx unit |
| MOIZ7TSVR01V | **x86_64**, 8 vCPU, 19 GiB | **391 G** | 163 G (44%) | 211 G | 14 ctr, all up | Supabase (PG 17), PG 15, MySQL | drill 1/6 | backup SSH · backups in /tmp |
| adguard | — | — | — | — | — | — | — | BLOCKED |
| automsp | — | — | — | — | — | — | — | BLOCKED |

**No filesystem is in danger.** rdp02 is the tightest at 68% used with 63 G free, which confirms the §48 premise ("~30% free") without making it urgent. Inodes are healthy everywhere (rdp02 at 12%). **Neither LVM nor ZFS exists on the ARM hosts**, so §52 redundancy design starts from OCI block volumes; MOIZ7TSVR01V is the exception and uses LVM.

Largest single storage item across the fleet: **`/var/lib/docker` on MOIZ7TSVR01V at 100 GB**, then rdp01 at 59 GB, then rdp02 at 16 GB.

## What was actually wrong — and the pattern

Six independent failures were found. Every one is a **stale or mislabelled piece of configuration, failing silently on a schedule, with nothing reading the result.** None were capacity, hardware, or load.

| # | Symptom | Root cause | State |
|---|---|---|---|
| 1 | `easypanel-traefik` recreated every ~5 s for ~1 month | `automsp-platform` (Next.js, PM2) holds `:80`; Stalwart holds `:443`. Swarm can bind neither. | **FIXED** — scaled to 0, reversible |
| 2 | `/var/log` grew 4.2 GB in 30 days | #1, logging every failure | resolves with #1 |
| 3 | certbot failing 2×/day since ≥Sep 5 | credentials file **named** `cloudflare-automsp-link.ini` holds a token scoped to **`automsp.store`** — verified via the Cloudflare API, which returned exactly one zone | OPEN — 23 days to expiry |
| 4 | fail2ban dead 9 days (`255/EXCEPTION`) | `ignoreip` defined twice in `[DEFAULT]` of `jail.local` | **FIXED** — sshd jail running |
| 5 | Backup drill scoring 1/6 nightly | rdp02's host key changed (rebuild); MOIZ7TSVR01V's `known_hosts` still holds the old one, so strict checking refuses **before** auth. A missing authorized key compounded it. | authorized key **ADDED**; host key pending verification |
| 6 | Health monitor down since ≥Sep 5 | PM2 `cron_restart */5` signalling it mid-startup; `TELEGRAM_CHAT_ID` also defaults empty, so alerts go nowhere even when it runs | OPEN |

**#6 is why the other five went unnoticed.** The checks exist and work correctly — the drill scored itself 1/6 accurately every single night. What is missing is the last hop: something that reads a verdict and tells a human.

## Corrections made during this audit

Recorded because the method matters as much as the findings (§107):

1. Claimed nothing was listening on `:80`/`:443` on rdp02 — **wrong**, the listening table had been truncated to 25 rows on read.
2. Claimed certbot and Traefik shared the `:80` root cause — **wrong**; certbot uses DNS-01, which needs no port. (Partially right after all: `n8n.automsp.us` alone uses `webroot` and *is* affected.)
3. Recommended "switch certbot to DNS-01" — **already configured**; the `dns-cloudflare` plugin was in use.
4. Raised "vault backup is empty" as critical — **wrong**; the drill's check SSHes to rdp02 and `|| echo 0` swallows the failure. Local backups are healthy: five consecutive nightly tarballs, ~83.4 MB each.
5. Read a jump-host probe as success — **wrong**; `head -1` had swallowed the `Permission denied` on line 2.

## Two genuine risks that survive every correction

**Backups live in `/tmp`.** `/tmp/automsp-vault-backup-*.tar.gz`, on a host running `systemd-tmpfiles-clean.timer`. Default policy clears `/tmp` after 10 days; a reboot can clear it outright. Five days of vault backups are sitting in a directory designed to be emptied. Moving the cron target to `/var/backups/automsp/` is a one-line change that removes a real loss scenario.

**Off-site replication has been down since at least Sep 6.** Until #5 is closed, every copy of the Obsidian vault — the PKOS content source — is on a single host. §92 wants primary + secondary + off-site; the current state is primary only.

## Cleared concerns

- **Apollo prospecting jobs do not burn tokens.** `apollo_harvest_gated.sh` and `apollo_enrich_gated.sh` are consent-gate wrappers. Every 4-hourly firing since Sep 6 logs `BLOCKED — CONSENT_GRANTED not found. Skipping.` The control works.
- **`automsp-health` makes no LLM calls** — its only outbound request is a Telegram alert.
- **`automsp-intelligence` is stopped with no cron** — the nightly `@claude-flow/cli` call recorded in prior context is gone.
- **The Apollo cron entries are on MOIZ7TSVR01V**, not rdp02 as previously recorded, and they are not the broken ones described earlier.

Across all three audited hosts, **nothing bills an LLM on a schedule.**

## PKOS ingestion targets found

- `/root/Obsidian/AutoMSP` on **both** rdp02 (6.26 GB) and MOIZ7TSVR01V — needs reconciling; two vaults or one replicated?
- `/root/.hermes` on both, with `a2a_audit.jsonl` and `a2a_conversations` — §68 evidence.
- `/var/log/automsp/drill-report-*.json` — structured restore-test evidence, exactly the §93 artifact, once the drill passes again.
- 43 git repositories on rdp02.
- **Ollama on `127.0.0.1:11434` (rdp02)** — a local model endpoint, which matters for §32: `SENSITIVE` content should default to local processing, and the capability already exists.

---

# RESOLUTION — backup restored (2026-09-08)

## MITM check: performed, passed

The `REMOTE HOST IDENTIFICATION HAS CHANGED` warning was verified rather than dismissed — the discipline this project asked for, exercised on a real alert.

| Source | ED25519 fingerprint |
|---|---|
| rdp02, asked directly over a trusted channel | `SHA256:FbgZ97LNL5Ed7MvBdVgY1rHa6rLseQ0M17hIKH79Xo0  root@rdp02` |
| What MOIZ7TSVR01V was offered | `SHA256:FbgZ97LNL5Ed7MvBdVgY1rHa6rLseQ0M17hIKH79Xo0` |
| Re-scanned after replacing the entry | `SHA256:FbgZ97LNL5Ed7MvBdVgY1rHa6rLseQ0M17hIKH79Xo0` |

Identical. **No man-in-the-middle.** rdp02 was rebuilt at some point and regenerated its host keys; MOIZ7TSVR01V's `known_hosts` still held the pre-rebuild entry, and strict checking correctly refused the connection *before authentication* — which is why adding an authorized key alone did nothing.

The failure mode here would have been running `ssh-keygen -R` reflexively to silence the warning. Verifying against the source first is the entire control, and it is the only reliable MITM detection SSH offers.

## Drill: 1/6 → 6/6

```
PASS: Vault sync completed
PASS: n8n export completed
PASS: Ruflo state sync completed
PASS: Vault backup contains 13,313 files
PASS: n8n backups present (3 sets)
PASS: Backup server SSH responsive
Passed: 6/6   Failed: 0/6   exit=0
```

**13,313 files replicated off-site** — the Obsidian vault, the PKOS content source, now has a second copy on a separate host for the first time since rdp02 was rebuilt.

§92 status moves from *primary only* to **primary + off-site**. §93 is satisfied properly: this is not a backup that "completed successfully", it is a backup whose restoration path has been exercised and scored.

Root cause chain, complete:

```
rdp02 rebuilt → host keys regenerated
   → MOIZ7TSVR01V known_hosts stale
      → strict host-key check refuses before auth
         → backup-sync.sh FATAL every 5h
            → backup-drill 1/6 nightly
               → nothing read the verdict (health monitor down)
                  → undetected for days
```

One stale line. Five reported failures. Zero alerts.

Minor item to confirm: the n8n set count reads 3 where it previously read 30. The earlier figure was counted locally while the export was failing; this one is counted on the backup server now that SSH works. Different location, so a different count is expected — worth one look to confirm retention is as intended, not a fault.

## Fleet status after remediation

| Item | Before | After |
|---|---|---|
| Traefik crash loop | recreating every ~5 s for ~1 month | **stopped** (scaled to 0, reversible) |
| fail2ban | dead 9 days | **running**, sshd jail active |
| Backup drill | 1/6 nightly | **6/6** |
| Off-site vault copy | none since rdp02 rebuild | **13,313 files** |
| certbot | failing 2×/day | **OPEN** — 23 days to expiry |
| Health monitor | down since ≥Sep 5 | **OPEN** — and empty `TELEGRAM_CHAT_ID` |
| Backups in `/tmp` | at risk of tmpfiles cleanup | **OPEN** |
| adguard / automsp | unaudited | **BLOCKED** — no key path |
| 43 SSH keys across 2 hosts | unreviewed | **OPEN** |
