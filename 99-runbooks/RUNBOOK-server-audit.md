# RUNBOOK — PKOS Server Audit (Phase 1)

**Script:** `pkos-server-audit.sh` · **Schema:** `pkos.server-audit/1.0.0`
**Status of this phase:** `AWAITING_HUMAN_EXECUTION` — this is the blocking gate for SOW Phases 1 and 2.

---

## Can you just give Claude SSH access? No — and here is the measurement

Asked directly and tested exhaustively on 2026-09-07. **Port 22 is refused by the platform's egress policy**, with valid proxy credentials, on every available path:

| Path | Result |
|---|---|
| SOCKS5 `CONNECT 150.136.95.118:22` via sanctioned proxy (authenticated) | **`CONNECTION NOT ALLOWED BY RULESET`** |
| HTTP proxy `CONNECT :22` (authenticated) | **`CONNECTION NOT ALLOWED BY RULESET`** |
| Cloud container raw TCP `:22` | blocked |
| Desktop VM raw TCP `:22` | `Network is unreachable` |
| Desktop VM `ssh` binary | present, but has no route |
| Cloud container `ssh` binary | not installed |

For contrast, these **do** work, which proves the block is port-specific rather than a general network failure: the cloud container completes a full TLS handshake to `150.136.95.118:443` and sees your real certificate (`CN=automsp.us`); ports 80 and 443 are reachable end-to-end.

So there is no key you can give me, no config you can change on your server, and no firewall rule that grants Claude an SSH session. The block is on Anthropic's side and is not something to work around. **Every option below gets the data out without SSH-from-Claude.**

## Why you are running this and not Claude

Neither shell available to the assistant can reach your servers. This was measured, not assumed:

| Path | Result |
|---|---|
| Cloud container → `150.136.95.118:22` | blocked |
| Cloud container → `132.145.133.39:22` | blocked |
| Cloud container → `https://150.136.95.118` | proxy returned **403** (policy denial) |
| Cloud container `ssh` binary | **not installed** |
| Laptop VM (`device_bash`) → both IPs | `Network is unreachable` |
| Laptop VM `tailscale` binary | **not installed** |

Your Tailscale runs on the Windows host, not inside the VM the assistant gets a shell in. So the audit has to be executed by you. There are five servers per the SOW; only two IPs appear in prior context, and **the set of five is unconfirmed** — part of your job here is to tell us what actually exists.

---

## What this script will NOT do

It is strictly read-only. Verified by automated grep against the source, all passing:

- no `rm` (except its own `mktemp -d` scratch dir), no `mv`, `dd`, `mkfs`, `truncate`, `shred`, `unlink`
- no `docker rm/rmi/prune/stop/kill/start/restart` — Docker is **inventoried only**
- no `systemctl start/stop/restart/enable/disable`
- no `apt`/`yum`/`snap`/`pip install|remove|update`
- no `kill`/`pkill`, no `crontab -r`, no `sudo`
- **no network calls at all** — no curl, wget, apt update, or cloud metadata endpoint. Runs fully offline.
- never prints the contents of a private key, `.env`, token, or password. It reads *specific sshd directives* and lists *filenames* only.
- never opens or extracts an archive — paths, sizes and mtimes only.

It writes exactly one file: the JSON report.

---

## Run it — three ways, best first

### Option 1 (recommended): one command, output lands straight in the shared folder

From **your** machine, where Tailscale and SSH already work. Run it from inside the connected project folder:

```bash
cd "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos"
mkdir -p 90-evidence/servers

ssh root@150.136.95.118 "bash -s -- --out /dev/stdout" \
    < 99-runbooks/pkos-server-audit.sh \
    > 90-evidence/servers/optimus-prime-audit.json
```

Progress goes to stderr (you watch it live); the JSON goes to stdout and lands in the folder I can read. Nothing is copied onto the server and nothing is left behind.

Repeat per server, changing the host and the output filename. Then tell me, and I run `secondbrain ingest server-audit 90-evidence/servers/`.

> The `bash -s` form was specifically hardened for this: every command inside the script runs with `</dev/null`, so no child process can swallow the script text while bash is still reading it from stdin. Without that guard this exact pattern hangs — it was caught in testing, not in production.

### Option 2: copy, run, copy back

If you would rather keep a copy on the server, or the pipe misbehaves on a particular box:

```bash
scp 99-runbooks/pkos-server-audit.sh root@150.136.95.118:/tmp/
ssh root@150.136.95.118 'bash /tmp/pkos-server-audit.sh --out /tmp/audit.json'
scp root@150.136.95.118:/tmp/audit.json 90-evidence/servers/optimus-prime-audit.json
```

### Option 3: interactive, with Claude driving your terminal

If you want me to run ad-hoc commands rather than a fixed script — chasing something the audit surfaces, say — I can drive **Windows Terminal on `moizsrtlap01`** through the desktop's computer-use tools. You approve the app once, I type into your terminal, and your Tailscale connection does the reaching.

Honest limits: I read the results from screenshots, so it is fine for short commands and answers, and poor for anything that dumps a lot of text. Use Option 1 for the audit itself and keep this for follow-ups.

### Paste-only fallback

For a box you can only reach through a web console:

```bash
cat > /tmp/pkos-server-audit.sh <<'PKOS'
<paste the entire script here>
PKOS
bash /tmp/pkos-server-audit.sh
```

**Run as root** for full coverage. Non-root still works — Docker, per-user crontabs and some `du` paths degrade to `"status":"REQUIRES_ROOT"` rather than failing, and every one of those is logged in `.errors`.

Options: `--out /path/report.json` (default `/tmp/pkos-audit-<host>-<UTC>.json`), `--timeout 45` (per-command seconds; raise to 90 on a slow or very full disk).

**Expected runtime:** 20–90 s on a healthy box; up to ~4 min on one with a large `/var/lib/docker` or millions of small files. It never hangs — every slow command is wrapped in `timeout`, and a section that expires records `"status":"TIMEOUT"` and the run continues.

---

## Verify the output before sending it back

```bash
python3 -m json.tool /tmp/pkos-audit-*.json > /dev/null && echo "VALID JSON"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('host',d['host'],'root',d['ran_as_root'],'errors',d['error_count'])" /tmp/pkos-audit-*.json
```

A valid report has all of: `identity, storage, heatmap, docker, archives, databases, services, scheduled, age_profile, backups, security_surface, pkos_probes, errors`.

**`error_count` > 0 is normal and expected** — missing binaries, unreachable daemons and root-only sections all land there deliberately. Per SOW §43 a section is never silently omitted; if something didn't run, `.errors` says why. An audit reporting zero errors on a box without ZFS or LVM would be the suspicious one.

---

## Where to put the results

Drop each file into this folder on your laptop:

```
AutoMSP BOS Claude Project\pkos\90-evidence\servers\<hostname>-audit.json
```

Then tell me. Also tell me:

1. **How many servers actually exist** — the SOW says five; two IPs are known. Names/IPs for the rest.
2. **Which one is the "Second Brain" server** with ~30% free storage (SOW §48). The audit flags any filesystem at ≥70% used in `storage.low_free_filesystems`, so it will identify itself, but confirm which box you meant.
3. **Any server you could not run this on**, and why — that becomes a `BLOCKED` entry in the source registry rather than a silent gap.

---

## What happens next

Once the JSON lands, Phases 1 and 2 unblock and produce, from real numbers rather than assumption:

- Five-Server Infrastructure Audit (SOW §127.4) and the Server Matrix (§102)
- Storage Heatmap (§127.5)
- Docker Cleanup Report (§127.6) — inventory and **dry-run proposal only**; nothing is deleted without the §97 gate: dry run → impact report → dependency analysis → backup check → your explicit approval
- Archive Cleanup Report (§127.7), same gate
- A RAID/redundancy assessment (§52), stated plainly as redundancy, **not** backup

Nothing destructive happens on any server without you approving a specific, itemised plan first.
