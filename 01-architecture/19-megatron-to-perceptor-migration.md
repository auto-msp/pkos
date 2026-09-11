# Migrating the operating home: Megatron → Perceptor

**Goal (stated 2026-09-08):** operate from Perceptor (rdp01, 132.145.133.39).
Megatron (MOIZ7TSVR01V, 100.80.47.37) keeps its copy of the files as a cold
backup — **nothing on Megatron gets deleted.**

---

## What is actually running on Megatron

Megatron is not a spare box. It is a live workstation with a desktop session,
and four different things write to the vault.

| What | Detail |
|---|---|
| **Obsidian desktop app** | `/opt/Obsidian/squashfs-root/obsidian`, running under an X/VNC session |
| **n8n** | `node /usr/local/bin/n8n` as user `coreitx`, 1.6 GB RSS — writes workflow backups into `vault/backups/n8n/` |
| **Apollo consent gate** | writes `vault/outbound/logs/consent_gate.log` |
| **Vault at** | `/root/Obsidian/` — 5.2 GB, 61,512 files |

Outbound replication currently alive:

| Schedule | Job | Target |
|---|---|---|
| every 15 min | `obsidian-vault-backup.sh` | git commit+push `/root/Obsidian/AutoMSP` → `github.com/automspai/automsp-vault.git`, **and** rsync all of `/root/Obsidian/` → **rdp02** (150.136.95.118) |
| daily 07:00 | `vault-sync-to-staging.sh` | rsync `vault/` → **Ratchet** (141.148.58.44), then `npm install`, `pm2 restart automsp-staging`, health-check `:3100` |
| ~~daily 02:00~~ | ~~tarball + rclone → Google Drive + rsync → Ratchet~~ | **removed 2026-09-08** |

Two corrections worth recording, because both were wrong on first reading:

1. Removing the 02:00 line did **not** cost the Ratchet replica — the 07:00 job
   rsyncs to the same target. The only real loss was the **Google Drive**
   off-tenancy copy.
2. `vault-sync-to-staging.sh` is **not a backup**. It is a deployment pipeline:
   rsync → npm install → pm2 restart → health check. Moving it is a deploy
   migration, not a file copy. Its name hides that.

---

## What "operate from Perceptor" requires

Five separate pieces of work. Only the first is finished.

| # | Piece | State |
|---|---|---|
| 1 | **Vault data on Perceptor** | ✅ 5.2 GB / 61,512 files verified — but now hours stale, and at the wrong path |
| 2 | **Obsidian app on Perceptor** | ⬜ not installed; Perceptor does have a desktop session (`.vnc`, `.xsession`) |
| 3 | **Replication jobs** | ⬜ need the scripts, an SSH key that reaches rdp02 + Ratchet, and GitHub push credentials |
| 4 | **Off-site backup** | ⬜ `rclone not found` on Perceptor; the Google Drive remote needs an OAuth grant only Moiz can give |
| 5 | **n8n** | ⬜ its own migration — workflows, credentials, database, and any inbound webhook URLs |

**Path collision:** Perceptor already has `/root/Obsidian` — 307 MB, dated
July 8, owned by `ubuntu`, not a git repo. It is a stale partial copy and it
occupies the exact path every script expects. It gets moved aside, never
deleted.

---

## Order of work

Phases A and B change nothing that is running. Phase C is the only one that
needs a quiet window.

### Phase A — make Perceptor's copy current, at the right path
1. `mv /root/Obsidian → /root/Obsidian.stale-july-2026` on Perceptor (kept)
2. `mv /root/vault-from-megatron → /root/Obsidian` so every script's hard-coded
   `/root/Obsidian/...` resolves without editing a single path
3. Delta rsync Megatron → Perceptor (no `--delete` yet; deletion is a cutover
   decision, not a refresh decision)

### Phase B — put the tooling in place (still no cutover)
4. Copy `/root/bin/*.sh` to Perceptor
5. Install rclone; **Moiz** authorises the Google Drive remote
6. Give Perceptor SSH access to rdp02 and Ratchet, and GitHub push rights
7. Install Obsidian on Perceptor

### Phase C — the cutover (needs a window)
8. Quiesce writers on Megatron: quit Obsidian, pause n8n's vault writes,
   comment out both cron lines (comment — never delete)
9. Final delta rsync **with** `--delete`
10. Verify: file count, byte count, and a sampled checksum comparison
11. Enable the jobs on Perceptor — **each cron line shown and approved first**
12. Start Obsidian on Perceptor; repoint n8n's backup path
13. Megatron's copy freezes as the cold backup

### Phase D — n8n
Separate migration. n8n holds workflows, credentials and its own database, and
anything calling an inbound webhook will keep calling Megatron until those URLs
move. Not something to fold into a vault cutover.

---

## The rule that governs this

The vault has **two live writers on Megatron** (the Obsidian app and n8n). The
moment a second copy also accepts writes, the two diverge, and reconciling
61,512 files by hand is far worse than any delay. So Perceptor is a **replica
until the cutover instant**, and becomes authoritative only once Megatron's
writers are stopped — never both at once, never "for now".
