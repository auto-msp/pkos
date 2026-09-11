# 4. Server Audit — rdp02 (150.136.95.118, "Optimus Prime")

**SOW §47, §48, §102 · audited 2026-09-07, as root, 8m27s, 14 recorded exceptions**
**Status: `COMPLETED` for this host. 4 of 5 servers still `NOT_STARTED`.**

## Identity

Ubuntu 24.04.4 LTS · kernel 6.17.0-1018-oracle · **aarch64 (ARM)** · KVM · 4 vCPU · 23 GiB RAM (13 GiB used, 10 GiB available) · TZ Asia/Kolkata · up 6 weeks 5 days.

**The §48 premise is confirmed:** `/dev/sda1` is 193 G, **130 G used, 63 G free — 68% used, 32% free.** This is the Second Brain server the SOW describes. My ≥70% flag missed it by two points, so `low_free_filesystems` came back empty — the threshold is wrong for this box, not the concern.

Inodes are healthy: 2,946,755 of 26,083,328 used (**12%**). No inode pressure.

---

## Act on these five

### 1. `easypanel-traefik` is in a crash loop — live, right now

Six `traefik:3.6.7` containers in state `Created`, aged **less than 1s, 5s, 11s, 16s, 22s, 27s** at audit time. That is a Swarm service being recreated roughly every 5 seconds and never reaching `Running`.

It is almost certainly also the answer to the next finding.

### 2. `/var/log` wrote 4.2 GB in 30 days

Age profile: `/var/log` holds **128 files, 4,222,082,084 bytes in the 0-30d bucket** and almost nothing older. That is not normal log volume for this workload — it is a service logging a failure several times a minute. Fix #1 and this stops growing on its own.

### 3. 22 SSH keys can reach this box — 18 of them as root

```
/root/.ssh/authorized_keys      18 keys
/home/ubuntu/.ssh/authorized_keys  3 keys
/home/opc/.ssh/authorized_keys     1 key
```

**Eighteen keys with root.** Every one is a person or machine that can become root here. This is the highest-value security item on the server, well above anything about sessions or MITM: `PasswordAuthentication no` is set and fail2ban is running three jails, so the front door is sound — the question is who already holds a key.

`pkos-session-forensics.sh` prints each key's fingerprint and comment. Go through all 22 and name every one. Any you cannot name is the finding.

### 4. `certbot.service` has FAILED — certificate renewal is broken

`certbot.timer` is scheduled and firing, but `certbot.service` is in a `failed` state. Certificates that stop renewing fail silently until something goes dark. Check expiry dates before anything else on this list bites.

### 5. There is no current backup — and that blocks Phase 2

`rclone` and `mysqldump` are installed, but nothing is scheduled. `/var/backups` holds 2.8 MB of dpkg metadata only. The newest real backup artifacts are **2026-06-17 — nearly three months old** (`/home/ubuntu/automsp-backup/vault/AutoMSP-BOS-*.tar.gz`) plus a `clawd` tarball from 2026-03-21.

§93 and my own roadmap gate say the same thing: **no storage remediation runs until a backup exists and a restore has been verified.** With 63 G free there is no urgency to delete anything, so this ordering costs nothing.

---

## Docker (SOW §50) — inventory only

**27 containers: 21 running, 6 in the traefik crash loop.** Docker 29.8.0, 19 images, 1 dangling.

Running workload: easypanel · automsp-portal + its Postgres 16 · n8n stack (n8n, worker, Postgres 15, Redis 7, cloudflared) · postgres-primary + pg-haproxy + pg-healthcheck + pgadmin4 · odoo19-crm + Postgres 15 · stalwart (mail) · linkedin-scraper · paperclip + Postgres 17 · litellm-proxy · cloudflared · nginx-mariadb.

**That is five separate PostgreSQL instances** (15, 15, 16, 17, plus primary 16) on one 4-vCPU box, alongside Odoo, n8n, a mail server and an LLM proxy. Worth a consolidation conversation later; not urgent.

**3 orphan volume candidates** — referenced by no container:

```
clawdbot_clawdbot-data
evolution-api_evolution_evolution-instances
n8n_data
```

**Do not delete `n8n_data` on the strength of this.** The running n8n stack uses a Postgres backend, so the named volume may be a leftover from a pre-Postgres deployment — or it may hold the encryption key and legacy workflow data. §97 gate applies in full: dry run → impact report → dependency check → verified backup → your approval. All three are candidates for *investigation*, not removal.

Container restart counts are all **0** across the running set — the workload is stable. Only the traefik service is churning, and it churns by recreation rather than restart, which is why the restart counter does not catch it.

---

## Exposure (SOW §26–§31)

**Sound:** `PasswordAuthentication no` in both sshd config files · fail2ban with `sshd`, `nginx-http-auth`, `nginx-limit-req` jails · 307 iptables rules + 124 NAT rules · Tailscale up on 100.93.108.65 · Ollama bound to **127.0.0.1** only.

**Worth reviewing — services bound to `0.0.0.0`:**

| Port | Service |
|---|---|
| **5432** | odoo19-postgres |
| **5433** | postgres-primary |
| **5050** | pgAdmin 4 |
| 5678 | n8n |
| 8069 | Odoo |
| 3000 / 3002 | easypanel / automsp-portal |
| 5500 / 7000 | haproxy |
| 8001 / 8003 | uvicorn / python3 |
| 18789 | openclaw-gateway |

Three database-adjacent services listening on every interface. Whether they are actually reachable from the internet depends on the OCI security list and those 307 iptables rules — the audit cannot see the cloud firewall, so **this is exposure to verify, not a confirmed hole**. Binding them to `127.0.0.1` or the tailnet address would remove the question entirely.

**32 credential files** were located by name (contents never read). Several sit beside live services: `/root/automsp-platform/.env`, `/root/automsp-portal/docker/.env`, `/root/n8n_docker/.env`, `/root/.openclaw/credentials`, `/root/.flow-nexus/.key`, plus `private.pem` / `public.pem` in `/root`. Relevant to the outstanding key-rotation item.

**Login shells:** `root` (zsh), `ubuntu`, `opc`, and `jicofo` (uid 996 — a Jitsi service account with `/bin/bash`; service accounts normally should not have a login shell).

---

## Scheduled jobs (SOW §94) — the token-burn check

**Good news: the failing "Apollo Prospecting Queue" entries are gone.** Root's crontab now holds exactly two lines:

```
*/5 * * * *  cd /root/clawd && git add -A && git diff --cached --quiet || git commit -m 'Auto-backup ...' && git push origin master
@reboot      iptables -I FORWARD 1 -i br-+ -j ACCEPT && iptables -I FORWARD 1 -o br-+ -j ACCEPT
```

Both benign. `/etc/cron.d` holds only stock entries (certbot, e2scrub, php). Systemd timers are all stock plus a Datadog config downloader.

**One item needs a precise read, not a guess:** the PM2 process list contains seven managed apps — `automsp-bos`, `automsp-health`, `ruflo-coordinator`, `automsp-bos-portal`, `cf-tunnel-bos`, `automsp-platform`, `automsp-intelligence` — and **exactly one `cron_restart: */5 * * * *`**. My extraction could not reliably attribute that schedule to a specific app, so I am not going to name one. Confirm with:

```bash
ssh root@150.136.95.118 "pm2 jlist | python3 -c \"import json,sys;[print(a['name'],'->',a['pm2_env'].get('cron_restart')) for a in json.load(sys.stdin)]\""
```

Nothing here bills an LLM on a schedule, which was the concern.

---

## The disk mystery — and what the audit could not see

Three sweeps hit their 90-second bound and returned nothing: `du -x -d1 /`, `du -d2 /root /home`, and `find` for large files and archives.

The age profile explains why, and is the more interesting number:

| Path | Files | Bytes |
|---|---:|---:|
| **/root** 0-30d | 367,292 | 12.0 GB |
| **/root** 30-180d | **1,039,542** | **64.5 GB** |
| /root 180-365d | 102,221 | 2.6 GB |
| /root older | 9,997 | 1.6 GB |
| /home (all) | 201,784 | 8.6 GB |
| /opt (all) | 84,863 | 3.1 GB |

**`/root` alone holds roughly 80 GB across ~1.5 million files** — the bulk of the 130 GB used, and the reason `du` could not finish. Much of it is likely `node_modules` (43 git repos live on this box, and `paperclip/node_modules/.pnpm` already showed up in the archive scan), but that is inference, not measurement.

To get the missing breakdown, re-run just that piece with a longer bound:

```bash
ssh root@150.136.95.118 "timeout 900 du -x -d2 /root | sort -rn | head -40"
```

Other exceptions were all "binary not installed" and are informative rather than problems: **no LVM, no ZFS** (so §52 redundancy design starts from OCI block volumes, not a local pool), no `ufw` (iptables is managed directly), no host `psql`/`redis-server` (both live in containers), no `atq`.

---

## Also found — PKOS ingestion targets

- **Obsidian vault at `/root/Obsidian/AutoMSP`** — the second-brain content source referenced in prior context. A direct Phase 3 target.
- **Hermes at `/root/.hermes`** with `SOUL.md`, `auth.json`, `a2a_audit.jsonl`, `a2a_conversations` — the A2A setup is live and its conversation log is ingestible evidence (§68).
- **43 git repositories** on the host.
- **Ollama on 127.0.0.1:11434** — a local model endpoint, which matters for §32: `SENSITIVE` and `HIGHLY_SENSITIVE` content should default to local processing, and the capability is already here.

## Server matrix row (SOW §102)

| Server | Storage | Used | Free | Docker | Databases | Old data | Backups | Action |
|---|---|---|---|---|---|---|---|---|
| rdp02 | 193 G | 130 G (68%) | 63 G | 27 ctr / 19 img / 3 orphan vols | 5× Postgres, MariaDB, Redis | /root ~80 G, 1.5 M files | **stale — 3 months** | traefik loop · certbot · 18 root keys · backup |

Four servers remain unaudited. Same script, same three commands.

---

# Addendum — measured 2026-09-07, after the audit

## Traefik: confirmed dead, not merely slow

```
docker service ls  ->  easypanel-traefik   replicated   0/1   traefik:3.6.7
```

**`0/1` replicas.** Swarm cannot place a single working task, so it recreates one every ~5 seconds forever. Five more `Created` containers appeared between the audit and this check. This is what has been writing 4.2 GB of logs in 30 days.

**CORRECTION.** An earlier draft of this document claimed nothing was listening on 80 or 443. That was wrong — I had truncated the listening-socket table to 25 rows when reading it, and the answer was in the audit all along. The corrected finding follows.

### Root cause: ports 80 and 443 are already taken

```
docker service ps easypanel-traefik --no-trunc
  ERROR: "failed to bind host port 0.0.0.0:80/tcp: address already in use"
```

From the audit's own listening table:

```
tcp LISTEN *:80    users:(("next-server (v1...)", pid=1691744))
tcp LISTEN *:443   users:(("stalwart",            pid=3145208))
```

**A bare Next.js process owns port 80. The Stalwart mail server owns 443.** Traefik is a Swarm service that expects both, cannot get either, and is recreated every ~5 seconds forever.

**Three symptoms, one cause:**

1. Traefik crash-loop → cannot bind :80
2. 4.2 GB of `/var/log` in 30 days → the loop, logging every failure
3. `certbot.service` failed → HTTP-01 renewal also needs :80, and cannot have it

This is an architectural conflict, not a bug. Easypanel's model is that Traefik owns 80/443 and reverse-proxies everything behind it; instead two processes bound those ports directly. **Whoever wins the race at boot decides what is reachable.**

### The decision this forces

| Option | Consequence |
|---|---|
| **A.** Move the Next.js app to a high port; let Traefik own 80 | Restores the intended ingress. Fixes certbot. Requires knowing which PM2 app it is and updating its config. |
| **B.** Move Stalwart off 443 | Needed for A to fully work — Traefik needs 443 for TLS termination. Mail clients using 443 must be repointed. |
| **C.** Remove easypanel/Traefik | Valid if the Next.js app *is* the live site and Traefik is vestigial. Stops the loop and the log growth immediately. Certbot still needs a :80 story. |

Identify the process holding :80 before choosing:

```bash
ps -p 1691744 -o pid,ppid,user,etime,args --no-headers
pm2 list
```

Do not kill it blind — if it is the live site, that is an outage.

## `/root` measured: 67.9 GB, and ~19.7 GB of it is rebuildable cache

The 900-second `du` finished in 7 seconds once the page cache was warm.

| Path | Size | Class (§118) |
|---|---:|---|
| `/root` total | **67.9 GB** | |
| `.cache/pip` | 4.93 GB | **REBUILDABLE** |
| `.npm/_cacache` | 3.99 GB | **REBUILDABLE** |
| `.cache/uv` | 3.67 GB | **REBUILDABLE** |
| `.cache/ms-playwright` | 2.75 GB | REBUILDABLE (needs re-download) |
| `.cache/camoufox` | 1.29 GB | REBUILDABLE (needs re-download) |
| `.npm/_npx` | 1.23 GB | **REBUILDABLE** |
| `.cache/autoresearch` | 0.94 GB | REBUILDABLE (verify first) |
| **cache subtotal** | **≈19.7 GB** | |
| `Obsidian` | 6.26 GB | **PERMANENT** — PKOS source |
| `gpt-sovits` | 6.12 GB | REFERENCE |
| `autoresearch/.venv` | 6.10 GB | REBUILDABLE (venv) |
| `venv310` | 6.04 GB | REBUILDABLE (venv) |
| `.nvm` | 5.89 GB | REFERENCE — multiple Node versions |
| `.hermes` + `.hermes-venv` | 3.66 GB | ACTIVE |
| `.local` | 2.61 GB | ACTIVE |
| `.claude` | 1.67 GB | ACTIVE |
| `marvel-voices-backup` | 1.49 GB | REQUIRES_REVIEW — sole copy? |
| `automsp-platform` | 1.39 GB | ACTIVE |
| `.config/manicode` | 1.29 GB | REQUIRES_REVIEW |
| `.rustup` | 1.23 GB | REFERENCE |

**Reclaiming ~19.7 GB moves the disk from 68% used to roughly 57%** — and none of it is knowledge. Package and browser caches are the textbook `REBUILDABLE` retention class: they regenerate on demand by definition.

Use the tool-native commands, never `rm -rf`, so each tool updates its own index:

```bash
pip cache purge          # ~4.9 GB
npm cache clean --force  # ~4.0 GB
uv cache clean           # ~3.7 GB
```

Those three are the safe ~12.6 GB. `ms-playwright` and `camoufox` are also rebuildable but require a re-download, so only clear them if nothing is mid-run against them.

**Even so, §97 applies:** dry run → impact report → dependency check → **verified backup** → your approval. With 63 GB free there is no pressure to rush this, and the backup gap (newest artifact 2026-06-17) should close first.

## Obsidian, measured

`/root/Obsidian` is 6.26 GB: `AutoMSP` 4.06 GB, `vault` 1.10 GB, and `vault-backup-20260906-201743` 1.11 GB — a backup taken **the day before this audit**. This is the second-brain content source and a direct Phase 3 ingestion target. It is `PERMANENT` retention; nothing here is a cleanup candidate.

---

# Addendum 2 — resolution and two new findings (2026-09-07)

## Traefik: stopped, reversibly

`docker service scale easypanel-traefik=0` → converged, 0/0 tasks. The 5-second respawn and the log growth are stopped. Nothing was deleted; `=1` restores it. The service definition remains for whenever the port question is settled.

**Port 80 owner identified:** PID 1691744 is a child of PM2 id 7 `automsp-platform` (v0.40.3, Next.js 16.3.1, 4 days uptime) — the live platform, bound directly to `:80`. Traefik had been losing that race for roughly a month.

## SECURITY: a live credential is hardcoded in source

`/root/automsp-bos/bos_health_monitor.py` line ~24 sets a **Telegram bot token as the default value of an `os.getenv()` call**:

```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "<LIVE TOKEN HARDCODED HERE>")
```

The value is deliberately not reproduced in this document (§28: never store a secret value in canonical data).

**Why this matters beyond the file itself:** the token was printed to a terminal and into a chat transcript during this investigation. That is the second recorded instance of this failure mode on this project — an earlier session leaked NVIDIA NIM, proxy and OpenRouter keys the same way. The host also carries 43 git repositories and a root crontab that runs `git add -A && git push` every five minutes against `/root/clawd`; if `/root/automsp-bos` has a remote, this token may already be in commit history.

**Actions, in order:**

1. Revoke and reissue the bot token via Telegram BotFather.
2. Move it to `/root/automsp-bos/.env`, referenced as `os.getenv("TELEGRAM_BOT_TOKEN")` with **no fallback literal** — a missing credential should fail loudly, never fall back to a committed one.
3. Check whether `automsp-bos` has a git remote and whether the token is in history (`git log -S` for the value). If it is, history rewrite or repo rotation is required — deleting the current line is not enough.
4. Add a pre-commit secret scan. This is the second occurrence; the control that prevents a third is automation, not intent.

**Process lesson for this project:** the leak happened because an investigation command ran `head -30` on an unknown file. Reading unknown files should grep for *patterns* without printing values, or pipe through a redactor. Recorded here so the ingestion pipeline inherits the rule (§32: redact before content leaves its trust zone).

## Certbot is NOT vestigial — and renewal is genuinely broken

Earlier hypothesis (that Cloudflare terminates TLS and certbot is decorative) is **wrong**. It manages three real certificates:

| Certificate | Expires | Days left |
|---|---|---:|
| `mailserver.automsp.link` | 2026-10-01 | **23** |
| `n8n.automsp.us` | 2026-10-08 | 30 |
| `nemoclaw.automsp.us` | 2026-10-15 | 37 |

All currently VALID. But Let's Encrypt renews at **30 days remaining**, and `mailserver.automsp.link` is at 23 days and has not renewed — so this is not a theoretical risk. The renewal window has already been missed once, and `certbot.service` is in a `failed` state.

The likely cause is the same port conflict: HTTP-01 needs to bind `:80`, which `automsp-platform` holds. Scaling Traefik to 0 did not free it.

**Recommended fix: switch to DNS-01 via the Cloudflare plugin.** These are `automsp.us` / `automsp.link` domains already behind Cloudflare, and DNS-01 needs no inbound port at all — it removes the conflict permanently rather than scheduling around it.

```bash
apt-get install python3-certbot-dns-cloudflare
# credentials file, chmod 600, NOT in any git repo
certbot renew --dns-cloudflare --dry-run
```

Confirm the actual failure first: `journalctl -u certbot -n 40 --no-pager` and `tail -60 /var/log/letsencrypt/letsencrypt.log`.

The mail-server certificate is the one to watch — Stalwart holds `:443`, and an expired mail cert breaks clients silently.

## `automsp-health`: no token risk, but monitoring is dead

Read in full. It checks PM2 processes, portal HTTP, n8n HTTP, coordinator cycle age and Docker containers, then alerts via Telegram. **The only outbound call is `requests.post` at line 135 — the Telegram alert. No LLM API is involved.** It cannot burn tokens; the 288-launches-a-day pattern is harmless on that axis.

But it is **`stopped`**, with 7 restarts and 1 unstable restart. The error log shows a `KeyboardInterrupt` during `import json` at 2026-09-05 06:50:00 — the process being signalled during startup, consistent with PM2's `cron_restart` killing it before it finishes initialising.

**So the health monitor that is supposed to alert you when things break has itself been down since at least 5 September** — which is a decent explanation for how a Traefik crash-loop and a missed certificate renewal both went unnoticed. Restoring it is worth more than any single fix above.

Note also `TELEGRAM_CHAT_ID` defaults to an empty string. Even when the script runs, alerts go nowhere unless that variable is set in the environment.

---

# Addendum 3 — certbot root cause (2026-09-07)

## Correction: certbot and Traefik were NOT the same failure

Addendum 2 proposed that both stemmed from the `:80` conflict, and recommended switching certbot to DNS-01. **Both points were wrong.**

DNS-01 via Cloudflare is *already configured and already in use* — `dns-cloudflare` appears in certbot's discovered plugin registry and is the authenticator being invoked. And because DNS-01 never touches port 80, the port conflict is irrelevant to certbot. These are **two independent failures that happened to be visible at the same time**.

## The actual error

```
Failed to renew certificate mailserver.automsp.link with error:
Unable to determine zone_id for mailserver.automsp.link using zone names:
['mailserver.automsp.link', 'automsp.link', 'link'].
Please confirm that the domain name has been entered correctly and is
already associated with the supplied Cloudflare account.
```

Certbot walked the name upward — `mailserver.automsp.link` → `automsp.link` → `link` — and **the Cloudflare API token it holds cannot see a zone for any of them.**

Failing twice daily since at least **Sep 5** (09:18, 16:54, Sep 6 01:52, 16:17, Sep 7 06:43). Certificate expires **2026-10-01 — 23 days**.

## What it is, narrowed by evidence

Only `mailserver.automsp.link` fails. `n8n.automsp.us` and `nemoclaw.automsp.us` are not erroring — though neither has been *attempted* yet, since only the `.link` cert is inside the 30-day renewal window. So the evidence points at **`automsp.link` specifically**, not at a broken token:

1. **Token scope excludes the zone.** Most likely. A token scoped to `automsp.us` cannot read `automsp.link`. Requires `Zone:Read` on the zone plus `DNS:Edit` to write the challenge record.
2. **`automsp.link` lives in a different Cloudflare account** from the one the token belongs to.
3. **The zone was removed** from Cloudflare, or never fully added (pending nameserver delegation).

`n8n.automsp.us` sits at exactly 30 days and will be attempted imminently — that attempt is a free test of whether the token covers `automsp.us`.

## Decisive test — reads the token, never prints it

```bash
CONF=/etc/letsencrypt/renewal/mailserver.automsp.link.conf
CRED=$(awk -F' = ' '/dns_cloudflare_credentials/{print $2}' "$CONF")
echo "credentials file: $CRED"
TOKEN=$(awk -F' *= *' '/api_token/{print $2}' "$CRED")
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.cloudflare.com/client/v4/zones?per_page=50" \
| python3 -c "import json,sys;d=json.load(sys.stdin);print('api success:',d['success']);[print('  zone:',z['name'],z['status']) for z in d.get('result',[])];print('errors:',d.get('errors'))"
```

The token is read into a variable and used in a header. **Only zone names are printed.** If `automsp.link` is absent from that list, cause 1 or 2 is confirmed and the fix is a token with the right scope — not a certbot change.

**Do not `cat` the credentials file.** It holds a live API token, and this project has now leaked credentials to a terminal twice.

## Fix path once the zone question is answered

- **Zone present, token scoped too narrowly** → issue a token with `Zone:Read` + `DNS:Edit` covering both zones, replace the credentials file (`chmod 600`, outside any git repo), `certbot renew --dry-run`.
- **Zone in another Cloudflare account** → either move it, or give that cert its own credentials file via `dns_cloudflare_credentials` in its renewal conf.
- **Zone genuinely gone** → decide whether `mailserver.automsp.link` still needs a certificate at all. Stalwart holds `:443`; an expired mail certificate fails quietly on clients rather than loudly in a browser, which is why this went unnoticed for a month.

23 days of margin. Not an emergency today, and not something to leave for three weeks.

## Certbot: RESOLVED to root cause — mislabelled credential, all three certs at risk

```
credentials file: /root/npm/letsencrypt/cloudflare-automsp-link.ini
api success: True
  zone: automsp.store  active
errors: []
```

**The token is valid. It can see exactly one zone: `automsp.store`.**

The file is named `cloudflare-automsp-link.ini` but holds a token scoped to a *different domain*. A mislabelled credential — the failure mode that survives review precisely because the filename says what you expect.

**This is not a one-certificate problem.** Certbot has three certs across three zones, and the visible token covers none of them:

| Certificate | Zone needed | Token sees it? | Expires |
|---|---|---|---:|
| `mailserver.automsp.link` | `automsp.link` | **no** | 2026-10-01 (23 d) |
| `n8n.automsp.us` | `automsp.us` | **no** | 2026-10-08 (30 d) |
| `nemoclaw.automsp.us` | `automsp.us` | **no** | 2026-10-15 (37 d) |

Only the `.link` cert has failed *so far* because it is the only one inside its 30-day renewal window. `n8n.automsp.us` sits at exactly 30 days and is due imminently — **expect it to fail next**, unless its renewal conf points at a different credentials file.

Check whether the `.us` certs use a different token:

```bash
grep -H 'authenticator\|credentials' /etc/letsencrypt/renewal/*.conf
```

At least four zones are in play across this estate — `automsp.us`, `automsp.link`, `automsp.store`, `automsp.cloud` — so "which token covers which zone" needs to be answered once, deliberately.

### Fix

Issue one Cloudflare API token with **`Zone:Read` + `DNS:Edit`** across every zone certbot must renew (or account-scoped over all zones). Write it to a correctly-named file, `chmod 600`, **outside any git repository** — note the current one lives under `/root/npm/`, and this host runs a 5-minute `git add -A && git push` cron against `/root/clawd`. Then:

```bash
certbot renew --dry-run
```

A dry run exercises every certificate, so it proves all three at once rather than waiting for each renewal window to arrive and fail.
