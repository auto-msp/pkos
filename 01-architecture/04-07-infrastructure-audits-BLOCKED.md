# 4–7. Infrastructure Audits — Five-Server, Storage Heatmap, Docker Cleanup, Archive Cleanup

**Status: `BLOCKED` on evidence. Not written on assumption.**

These four deliverables share one blocker, so they share one document until that blocker clears.

---

## The blocker, stated precisely

No shell available to this session can reach the servers. Measured:

| Probe | Result |
|---|---|
| container → `150.136.95.118:22` / `132.145.133.39:22` | blocked |
| container → `https://<server-ip>` | proxy **403** (policy denial) |
| container `ssh` binary | not installed |
| laptop VM → both IPs | `Network is unreachable` |
| laptop VM `tailscale` / `docker` / `oci` | not installed |

Tailscale runs on the Windows host; `device_bash` runs in an isolated VM on that host with no route to the tailnet.

**A server audit written without server evidence would be fiction.** §107 forbids inventing platform state, §43 forbids declaring completion without measurable proof, and §97 forbids proposing deletions without a dependency analysis grounded in real data. So these documents contain the *method* and the *gate*, and will contain the *findings* once the JSON arrives.

## The unblock — prepared, tested, waiting

`pkos/99-runbooks/pkos-server-audit.sh` (415 lines, stdlib-only bash) plus `RUNBOOK-server-audit.md` and `server-audit-schema.md`.

Verified in the container before delivery: valid JSON output; graceful degradation on absent `docker`/`zfs`/`pm2`/LVM; 17 s runtime; zero hits on an automated grep for every mutating command (`rm` outside its own mktemp dir, `mv`, `dd`, `docker prune|rm|stop`, `systemctl start|stop|restart`, package installs, `kill`, `crontab -r`, `sudo`, and any network call).

You run it on each server, drop the JSON into `pkos/90-evidence/servers/`, then:

```bash
secondbrain ingest server-audit pkos/90-evidence/servers/
secondbrain servers          # renders the §102 Server Matrix
```

The ingest path is already proven — a genuine audit output was ingested end-to-end during testing (`host=vm`, `error_count=24`, all sections parsed).

## #4 Five-Server Infrastructure Audit — pending

The audit collects, per server: identity · storage bytes **and inodes** · bounded `du` heatmap · top-50 largest files · Docker inventory (containers with restart counts, images with dangling flags, volumes **with the containers referencing them**) · archives ≥1 MB · database presence and data-dir sizes · systemd units and listening sockets · **every scheduled mechanism** · file-age buckets · backup tooling and artifacts · security surface (directives and filenames only, never key material).

**The count of five is itself unverified.** Prior context yields two IPs, a separate list of three tailnet Linux nodes, and a fourth host `rdp02`/"Optimus Prime" — these do not obviously reconcile. Report which servers actually exist when you run this.

## #5 Storage Heatmap — laptop only

Laptop side is measured (deliverable #2): 11.05 GiB across 57,145 Downloads files, 6.78 GB classified INCLUDE, 0.67 GB of confirmed duplicates, **2.45 GB of installers (20.6%)**.

Server side is empty. §48 states the Second Brain server sits at ~30% free and calls that a capacity risk; the audit flags every filesystem at ≥70% used in `storage.low_free_filesystems`, so the affected box will identify itself rather than being assumed.

## #6 Docker Cleanup Report — pending, and gated twice

The audit **inventories only**. It captures `docker volume ls` alongside the set of volumes actually referenced by containers, so orphan detection is a set difference computed *downstream* — the script never decides a volume is unused and never acts.

Beyond that, §97 requires: discover → dry run → impact report → dependency analysis → backup check → **human approval** → execute → validate → audit. `secondbrain cleanup` refuses to run without `--dry-run` and exits 2. That refusal is deliberate and tested.

One known trap from prior context: on `132.145.133.39` the Voicebox container's attachment to `n8n-docker-caddy_default` is **not declared in its compose file** and is lost on every rebuild. A naive "unused network" cleanup there would break a working service in a way the compose file cannot explain. This is exactly why dependency analysis precedes deletion.

## #7 Archive Cleanup Report — partial

Laptop archives are inventoried but **their interiors were not examined**: 122 archive files in the Downloads INCLUDE set, plus 2.99 GB of archives in the project folder (`automsp-outreach-analytics-live-data.tar.gz` 6.1 MB, `automsp-outreach-analytics.tar.gz` 686 KB, and others). §51 requires knowing whether an archive is unique, redundant, backup, historical or recoverable **before** any removal decision — that needs a listing pass, which is queued, not done.

§125 non-negotiable: **never remove the sole surviving copy of valuable information.** The `.stale-backup` finding in deliverable #2 is the cautionary case — it looks redundant (82.4% byte-identical) and is not (18 genuinely drifted files).

## RAID ≠ backup (§52)

Deferred pending the audit, but the principle is fixed now: whatever redundancy scheme is chosen — ZFS mirror, RAIDZ, OCI block-volume replication — **it is redundancy, not backup**. It protects against device failure. It does not protect against deletion, corruption propagated by sync, ransomware, or a bad migration. Those need the versioned, off-site, restore-tested layers in deliverable #15, and §93: a backup is not valid until a restore has been verified. `secondbrain restore --verify` implements exactly that check and is already working.
