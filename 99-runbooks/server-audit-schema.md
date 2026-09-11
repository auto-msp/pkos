# `pkos.server-audit/1.0.0` — output schema

One JSON object per server per run. Consumed by the Phase 1/2 analysis to build the Server Matrix (SOW §102), Storage Heatmap, and the Docker/Archive cleanup reports.

## Envelope

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | `pkos.server-audit/1.0.0` |
| `generated_at_utc` | string | ISO 8601 UTC |
| `generator` | string | `pkos-server-audit.sh` |
| `host` | string | hostname — the join key across runs |
| `ran_as_root` | bool | coverage indicator; false means root-only sections are stubs |
| `notes` | string[] | machine-readable safety and interpretation caveats |
| `error_count` | int | number of exceptions; **> 0 is normal** |
| `errors` | object[] | `{section, reason}` — every skip, timeout and missing binary |

## The probe object

Almost every leaf is a uniform probe object, so consumers can treat them identically:

```json
{ "status": "OK|TIMEOUT|ERROR|unavailable|REQUIRES_ROOT",
  "exit_code": 0, "cmd": "df -hPT", "seconds": 45,
  "lines": ["raw stdout line", "..."] }
```

`lines` is raw command output, deliberately unparsed. Parsing happens downstream where it can be versioned and corrected without re-running the audit on production — this is the SOW §4 acquisition/processing separation applied to infrastructure evidence.

| status | meaning |
|---|---|
| `OK` | ran, exit 0 |
| `ERROR` | ran, non-zero exit — `exit_code` carries it |
| `TIMEOUT` | exceeded its bound; run continued |
| `unavailable` | required binary not installed |
| `REQUIRES_ROOT` | needs privilege the run didn't have |

## Sections

| Section | Key contents | SOW |
|---|---|---|
| `identity` | hostname, FQDN, kernel, os_release, uptime, timezone, cpu, memory, virtualization, cloud_hints (local files only) | §47 |
| `storage` | `df_bytes`, `df_inodes`, mounts, lsblk, swap, LVM (pvs/vgs/lvs), ZFS, mdstat, **`low_free_filesystems`** (≥70% used) | §48, §52 |
| `heatmap` | `root_depth1`, `var_depth2`, `hot_dirs`, `largest_files` (>50 MB, top 50), `largest_dirs_home_root` | §48 |
| `docker` | version, `system_df`, containers, **`container_restarts`**, `container_mounts`, images, `dangling_images`, volumes, **`volumes_in_use`**, `dangling_volumes`, networks, compose files | §50 |
| `archives` | tar/gz/zip/7z/bak/dump/sql >1 MB — size, mtime, path. Never opened. | §51 |
| `databases` | postgres/mysql/mongo/redis/sqlite presence + versions, DB names and sizes (passwordless local only), data dir sizes | §47, §86 |
| `services` | systemd system/user units, enabled, **failed**, listening sockets, pm2 jlist, top processes by RSS | §47, §94 |
| `scheduled` | root + all user crontabs, `/etc/crontab`, `cron.d`, systemd timers (system and user), `atq`, **pm2 `cron_restart`** | §94 |
| `age_profile` | file count + bytes per age bucket (0-30d, 30-180d, 180-365d, 1-2y, 2y+) per major dir; large files unread 90 d | §49 |
| `backups` | tool presence (restic/borg/rclone/duplicity…), backup dirs, config **filenames**, ZFS snapshots, newest backup artifacts | §92, §93 |
| `security_surface` | sshd directives, ufw, iptables rule counts, fail2ban, login-capable users, sudoers filenames, authorized_keys **counts**, credential-file **names**, public-bound sockets | §26–§31 |
| `pkos_probes` | existing Obsidian vaults, git repos, vector/search stores, n8n, Hermes, python | §126.3, §109 |

## Cross-run joins

`host` joins runs; `generated_at_utc` orders them. Because volumes are captured alongside `volumes_in_use`, orphan detection is a set difference computed downstream — the script itself never decides that a volume is unused, and never acts on it.

## Deliberate omissions

No file contents. No secret values. No archive interiors. No database rows. No network reachability tests. Each is a downstream phase with its own approval gate.
