#!/usr/bin/env bash
# =============================================================================
#  PKOS SERVER AUDIT  --  STRICTLY READ-ONLY INFRASTRUCTURE INVENTORY
#  Personal Knowledge Operating System / Second Brain  --  Phase 1 (SOW 47-52)
#  Schema: pkos.server-audit/1.0.0
# =============================================================================
#
#  SAFETY CONTRACT  (read this before running as root)
#  ---------------------------------------------------------------------------
#  This script INSPECTS. It does not change anything.
#
#  IT WILL NOT:
#    * delete, move, rename, truncate or overwrite any pre-existing file
#    * chmod / chown anything
#    * start, stop, restart, enable or disable any service
#    * kill any process
#    * remove, prune or modify any Docker container, image, volume or network
#    * install, update or remove any package
#    * modify any crontab or systemd timer
#    * write to any database
#    * make ANY network call (no curl, no wget, no apt update, no metadata
#      endpoint). It runs fully offline on a firewalled box.
#    * print the contents of any private key, .env, credential file, token
#      or password. Only filenames and specific config DIRECTIVES are read.
#    * invoke sudo. Run it as root yourself if you want the root-only sections.
#
#  IT WILL WRITE exactly two things:
#    1. one JSON report at $OUT (default /tmp, override with --out)
#    2. a private temp dir from mktemp -d, removed on exit (its own files only)
#
#  Every potentially-slow command is wrapped in `timeout`. A section that
#  times out is recorded as {"status":"TIMEOUT"} and the run CONTINUES.
#  `set -e` is deliberately NOT used: a missing binary must degrade to
#  {"status":"unavailable"}, not abort the audit.
#
#  Filename includes hostname + UTC timestamp, so re-running never overwrites
#  a previous report.
# =============================================================================

SCHEMA_VERSION="pkos.server-audit/1.0.0"
TMO="${PKOS_TIMEOUT:-45}"          # per-command timeout, seconds
TMO_LONG="${PKOS_TIMEOUT_LONG:-90}" # for du / find sweeps
HOST="$(hostname 2>/dev/null || echo unknown-host)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null || echo unknown-time)"
OUT="/tmp/pkos-audit-${HOST}-${STAMP}.json"
IS_ROOT=0; [ "$(id -u 2>/dev/null)" = "0" ] && IS_ROOT=1

while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --timeout) TMO="$2"; shift 2 ;;
    --help|-h)
      echo "pkos-server-audit.sh [--out FILE] [--timeout SECONDS]"
      echo "Read-only. Writes one JSON report. Run as root for full coverage."
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Guard against stdin-piped invocation (`ssh host 'bash -s' < script`): no child
# may inherit the script text as its stdin. Individual commands are additionally
# run with </dev/null in capture()/capture_sh().
TMPD="$(mktemp -d 2>/dev/null)" || { echo "cannot create temp dir" >&2; exit 1; }
cleanup() { [ -n "$TMPD" ] && [ -d "$TMPD" ] && rm -rf -- "$TMPD"; }
trap cleanup EXIT INT TERM
# NOTE: the single `rm` in this script targets ONLY the mktemp dir this script
# created itself. It can never reach a pre-existing path.

# ---------------------------------------------------------------------------
# JSON emission helpers (hand-rolled: jq is NOT assumed to exist)
# ---------------------------------------------------------------------------
jesc() {
  local s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
  s="${s//$'\t'/\\t}"; s="${s//$'\r'/\\r}"; s="${s//$'\n'/\\n}"
  printf '%s' "$s" | tr -d '\000-\010\013\014\016-\037'
}
jarr_lines() {                    # stdin -> ["line","line",...]
  local first=1 line
  printf '['
  while IFS= read -r line; do
    [ $first -eq 1 ] && first=0 || printf ','
    printf '"%s"' "$(jesc "$line")"
  done
  printf ']'
}
have() { command -v "$1" >/dev/null 2>&1; }

SECTIONS=(); NOTES=()
ERRLOG="$TMPD/errors.jsonl"; : > "$ERRLOG"
add_section() { SECTIONS+=("\"$1\":$2"); }
# add_error writes to a FILE, not a bash array: capture()/capture_sh() are invoked
# inside $( ) command substitutions, which run in a subshell, so any array
# mutation there would be discarded. A file survives the subshell.
add_error()   { printf '{"section":"%s","reason":"%s"}\n' "$(jesc "$1")" "$(jesc "$2")" >> "$ERRLOG"; }
add_note()    { NOTES+=("\"$(jesc "$1")\""); }
join_by()     { local IFS="$1"; shift; printf '%s' "$*"; }

# capture(): run a command under timeout, return a JSON object describing it.
# $1 = required binary or "-" ; rest = argv
capture() {
  local req="$1"; shift
  local label="$*"
  if [ "$req" != "-" ] && ! have "$req"; then
    printf '{"status":"unavailable","reason":"%s not installed","cmd":"%s"}' \
      "$(jesc "$req")" "$(jesc "$label")"
    add_error "$label" "binary_not_installed:$req"
    return
  fi
  local out rc
  out="$(timeout "$TMO" "$@" 2>/dev/null </dev/null)"; rc=$?
  if [ $rc -eq 124 ]; then
    printf '{"status":"TIMEOUT","seconds":%s,"cmd":"%s","lines":[]}' "$TMO" "$(jesc "$label")"
    add_error "$label" "timeout after ${TMO}s"
  elif [ $rc -ne 0 ] && [ -z "$out" ]; then
    printf '{"status":"ERROR","exit_code":%d,"cmd":"%s","lines":[]}' "$rc" "$(jesc "$label")"
    add_error "$label" "exit_code:$rc"
  else
    printf '{"status":"OK","exit_code":%d,"cmd":"%s","lines":%s}' \
      "$rc" "$(jesc "$label")" "$(printf '%s\n' "$out" | jarr_lines)"
  fi
}
capture_sh() {                    # same, but for a shell pipeline string
  local tmo="$1" label="$2" script="$3"
  local out rc
  out="$(timeout "$tmo" bash -c "$script" 2>/dev/null </dev/null)"; rc=$?
  if [ $rc -eq 124 ]; then
    printf '{"status":"TIMEOUT","seconds":%s,"cmd":"%s","lines":[]}' "$tmo" "$(jesc "$label")"
    add_error "$label" "timeout after ${tmo}s"
  else
    printf '{"status":"OK","exit_code":%d,"cmd":"%s","lines":%s}' \
      "$rc" "$(jesc "$label")" "$(printf '%s\n' "$out" | jarr_lines)"
  fi
}
root_only() {                     # emit REQUIRES_ROOT stub when not root
  printf '{"status":"REQUIRES_ROOT","note":"%s"}' "$(jesc "$1")"
  add_error "$2" "requires root; ran as uid $(id -u 2>/dev/null)"
}

echo "[pkos-audit] host=$HOST root=$IS_ROOT out=$OUT" >&2
echo "[pkos-audit] read-only; no network; no deletions. starting..." >&2

# ===========================================================================
# 1. IDENTITY
# ===========================================================================
echo "[pkos-audit] 1/12 identity" >&2
{
  printf '{'
  printf '"hostname":"%s",' "$(jesc "$HOST")"
  printf '"fqdn":"%s",' "$(jesc "$(hostname -f 2>/dev/null || echo unknown)")"
  printf '"kernel":"%s",' "$(jesc "$(uname -sr 2>/dev/null)")"
  printf '"arch":"%s",' "$(jesc "$(uname -m 2>/dev/null)")"
  printf '"os_release":%s,' "$(capture - cat /etc/os-release)"
  printf '"uptime":"%s",' "$(jesc "$(uptime -p 2>/dev/null || uptime 2>/dev/null)")"
  printf '"boot_time":"%s",' "$(jesc "$(uptime -s 2>/dev/null)")"
  printf '"timezone":"%s",' "$(jesc "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null)")"
  printf '"audit_time_utc":"%s",' "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
  printf '"running_as_root":%s,' "$([ $IS_ROOT -eq 1 ] && echo true || echo false)"
  printf '"uid":"%s",' "$(jesc "$(id -u 2>/dev/null)")"
  printf '"cpu_count":"%s",' "$(jesc "$(nproc 2>/dev/null)")"
  printf '"memory":%s,' "$(capture - free -h)"
  printf '"virtualization":"%s",' "$(jesc "$(systemd-detect-virt 2>/dev/null || echo unknown)")"
  # cloud identity from LOCAL files only - never the metadata network endpoint
  printf '"cloud_hints":%s' "$(capture_sh 10 'local cloud hints' \
     'for f in /etc/oracle-cloud-agent/* /var/lib/cloud/data/instance-id /etc/cloud/cloud.cfg.d/*.cfg; do [ -e "$f" ] && echo "PRESENT: $f"; done 2>/dev/null; true')"
  printf '}'
} > "$TMPD/identity"; add_section identity "$(cat "$TMPD/identity")"

# ===========================================================================
# 2. STORAGE  (SOW 48: bytes AND inodes)
# ===========================================================================
echo "[pkos-audit] 2/12 storage" >&2
{
  printf '{'
  printf '"df_bytes":%s,' "$(capture df df -hPT)"
  printf '"df_inodes":%s,' "$(capture df df -iP)"
  printf '"mounts":%s,' "$(capture_sh 15 'mount table' "mount | grep -Ev '^(proc|sysfs|devtmpfs|cgroup|tmpfs|securityfs|pstore|bpf|tracefs|debugfs|configfs|fusectl|nsfs|mqueue|hugetlbfs)' ")"
  printf '"lsblk":%s,' "$(capture lsblk lsblk -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINT,UUID)"
  printf '"swap":%s,' "$(capture - swapon --show)"
  printf '"lvm_pvs":%s,' "$(capture pvs pvs)"
  printf '"lvm_vgs":%s,' "$(capture vgs vgs)"
  printf '"lvm_lvs":%s,' "$(capture lvs lvs)"
  printf '"zfs_pools":%s,' "$(capture zpool zpool list)"
  printf '"zfs_datasets":%s,' "$(capture zfs zfs list)"
  printf '"mdstat":%s,' "$(capture - cat /proc/mdstat)"
  # percent-free flags: SOW 48 treats <30% free as capacity risk
  printf '"low_free_filesystems":%s' "$(capture_sh 15 'filesystems under 30% free' \
     "df -hP | awk 'NR>1 { u=\$5; gsub(/%/,\"\",u); if (u+0 >= 70) printf \"%s used=%s%% avail=%s mount=%s\\n\", \$1, u, \$4, \$6 }'")"
  printf '}'
} > "$TMPD/storage"; add_section storage "$(cat "$TMPD/storage")"

# ===========================================================================
# 3. HEATMAP  (bounded du; SOW 48)
# ===========================================================================
echo "[pkos-audit] 3/12 storage heatmap (slow, bounded)" >&2
{
  printf '{'
  printf '"root_depth1":%s,' "$(capture_sh "$TMO_LONG" 'du -x -d1 /' \
     "du -x -d1 / 2>/dev/null | sort -rn | head -40")"
  printf '"var_depth2":%s,' "$(capture_sh "$TMO_LONG" 'du -x -d2 /var' \
     "du -x -d2 /var 2>/dev/null | sort -rn | head -40")"
  printf '"hot_dirs":%s,' "$(capture_sh "$TMO_LONG" 'du on known hotspots' \
     "for d in /var/lib/docker /var/log /var/lib/postgresql /var/lib/mysql /root /home /opt /srv /tmp /usr/local; do [ -d \"\$d\" ] && timeout 25 du -sh -x \"\$d\" 2>/dev/null; done")"
  printf '"largest_files":%s,' "$(capture_sh "$TMO_LONG" 'find largest files >50M' \
     "find / -xdev -type f -size +50M -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null | sort -rn | head -50")"
  printf '"largest_dirs_home_root":%s' "$(capture_sh "$TMO_LONG" 'du -d2 /root /home' \
     "du -x -d2 /root /home 2>/dev/null | sort -rn | head -30")"
  printf '}'
} > "$TMPD/heatmap"; add_section heatmap "$(cat "$TMPD/heatmap")"

# ===========================================================================
# 4. DOCKER  (SOW 50 - INVENTORY ONLY. This script never prunes.)
# ===========================================================================
echo "[pkos-audit] 4/12 docker" >&2
{
  printf '{'
  printf '"_policy":"inventory only - this script never prunes, removes or stops anything",'
  if ! have docker; then
    printf '"status":"unavailable","reason":"docker not installed"}'
  elif [ $IS_ROOT -eq 0 ] && ! docker info >/dev/null 2>&1; then
    printf '"status":"REQUIRES_ROOT","reason":"docker daemon not reachable as this user"}'
    add_error docker "docker present but daemon unreachable without root"
  else
    printf '"version":%s,' "$(capture docker docker version --format '{{.Server.Version}}')"
    printf '"system_df":%s,' "$(capture docker docker system df -v)"
    printf '"containers":%s,' "$(capture docker docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.RunningFor}}\t{{.Size}}\t{{.Ports}}')"
    printf '"container_restarts":%s,' "$(capture_sh "$TMO" 'container restart counts' \
       "docker ps -aq 2>/dev/null | while read -r c; do docker inspect --format '{{.Name}}\t restarts={{.RestartCount}}\t state={{.State.Status}}\t started={{.State.StartedAt}}' \"\$c\" 2>/dev/null; done")"
    printf '"container_mounts":%s,' "$(capture_sh "$TMO" 'container mounts' \
       "docker ps -aq 2>/dev/null | while read -r c; do docker inspect --format '{{.Name}}{{range .Mounts}} [{{.Type}} {{.Source}} -> {{.Destination}} rw={{.RW}}]{{end}}' \"\$c\" 2>/dev/null; done")"
    printf '"images":%s,' "$(capture docker docker images -a --format '{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}')"
    printf '"dangling_images":%s,' "$(capture docker docker images -f dangling=true --format '{{.ID}}\t{{.Size}}\t{{.CreatedSince}}')"
    printf '"volumes":%s,' "$(capture docker docker volume ls --format '{{.Name}}\t{{.Driver}}')"
    printf '"volumes_in_use":%s,' "$(capture_sh "$TMO" 'volumes referenced by containers' \
       "docker ps -aq 2>/dev/null | while read -r c; do docker inspect --format '{{range .Mounts}}{{if eq .Type \"volume\"}}{{.Name}}{{\"\\n\"}}{{end}}{{end}}' \"\$c\" 2>/dev/null; done | sort -u")"
    printf '"dangling_volumes":%s,' "$(capture docker docker volume ls -f dangling=true --format '{{.Name}}')"
    printf '"networks":%s,' "$(capture docker docker network ls --format '{{.Name}}\t{{.Driver}}\t{{.Scope}}')"
    printf '"compose_projects":%s' "$(capture_sh 20 'compose files on disk' \
       "find /root /home /opt /srv -maxdepth 4 -name 'docker-compose*.y*ml' -o -maxdepth 4 -name 'compose.y*ml' 2>/dev/null | head -50")"
    printf '}'
  fi
} > "$TMPD/docker"; add_section docker "$(cat "$TMPD/docker")"

# ===========================================================================
# 5. ARCHIVES  (SOW 51 - list only, never open or extract)
# ===========================================================================
echo "[pkos-audit] 5/12 archives" >&2
{
  printf '{'
  printf '"_policy":"paths, sizes and mtimes only - archives are never opened or extracted",'
  printf '"archives":%s' "$(capture_sh "$TMO_LONG" 'find archives' \
     "find / -xdev \( -path /proc -o -path /sys -o -path /dev -o -path /run -o -path /var/lib/docker/overlay2 \) -prune -o -type f \( -iname '*.tar' -o -iname '*.tar.gz' -o -iname '*.tgz' -o -iname '*.tar.bz2' -o -iname '*.tar.xz' -o -iname '*.zip' -o -iname '*.7z' -o -iname '*.bak' -o -iname '*.dump' -o -iname '*.sql' -o -iname '*.sql.gz' \) -size +1M -printf '%s\t%TY-%Tm-%Td\t%p\n' -print0 2>/dev/null | tr -d '\\000' | sort -rn | head -200")"
  printf '}'
} > "$TMPD/archives"; add_section archives "$(cat "$TMPD/archives")"

# ===========================================================================
# 6. DATABASES  (presence + sizes; never dumps data)
# ===========================================================================
echo "[pkos-audit] 6/12 databases" >&2
{
  printf '{'
  printf '"_policy":"presence, version and size only - no data is ever read or dumped",'
  printf '"postgres_present":"%s",' "$(jesc "$(command -v psql 2>/dev/null || echo no)")"
  printf '"postgres_version":%s,' "$(capture psql psql --version)"
  printf '"postgres_databases":%s,' "$(capture_sh 20 'psql list databases (passwordless local only)' \
     "if command -v psql >/dev/null 2>&1; then PGCONNECT_TIMEOUT=5 psql -U postgres -tAc \"select datname||' '||pg_size_pretty(pg_database_size(datname)) from pg_database order by pg_database_size(datname) desc\" 2>/dev/null || echo 'unavailable: no passwordless local connection'; else echo 'unavailable: psql not installed'; fi")"
  printf '"mysql_version":%s,' "$(capture mysql mysql --version)"
  printf '"mongo_present":"%s",' "$(jesc "$(command -v mongod 2>/dev/null || echo no)")"
  printf '"redis_version":%s,' "$(capture redis-server redis-server --version)"
  printf '"sqlite_version":%s,' "$(capture sqlite3 sqlite3 --version)"
  printf '"data_dir_sizes":%s' "$(capture_sh 40 'database data dir sizes' \
     "for d in /var/lib/postgresql /var/lib/mysql /var/lib/mongodb /var/lib/redis /var/lib/influxdb; do [ -d \"\$d\" ] && timeout 15 du -sh \"\$d\" 2>/dev/null; done")"
  printf '}'
} > "$TMPD/databases"; add_section databases "$(cat "$TMPD/databases")"

# ===========================================================================
# 7. SERVICES
# ===========================================================================
echo "[pkos-audit] 7/12 services" >&2
{
  printf '{'
  printf '"systemd_system_units":%s,' "$(capture systemctl systemctl list-units --type=service --all --no-pager --no-legend)"
  printf '"systemd_enabled":%s,' "$(capture systemctl systemctl list-unit-files --type=service --state=enabled --no-pager --no-legend)"
  printf '"systemd_failed":%s,' "$(capture systemctl systemctl --failed --no-pager --no-legend)"
  printf '"systemd_user_units":%s,' "$(capture_sh 20 'user units' "systemctl --user list-units --type=service --all --no-pager --no-legend 2>/dev/null || echo 'unavailable: no user session bus'")"
  printf '"listening_sockets":%s,' "$(capture ss ss -tulpn)"
  printf '"pm2_processes":%s,' "$(capture_sh 20 'pm2 jlist' \
     "if command -v pm2 >/dev/null 2>&1; then pm2 jlist 2>/dev/null | head -c 200000; else echo 'unavailable: pm2 not installed'; fi")"
  printf '"top_processes_by_rss":%s' "$(capture_sh 15 'top processes' "ps -eo pid,ppid,user,rss,etime,comm --sort=-rss 2>/dev/null | head -30")"
  printf '}'
} > "$TMPD/services"; add_section services "$(cat "$TMPD/services")"

# ===========================================================================
# 8. SCHEDULED  (CRITICAL - a past unknown cron burned an entire LLM budget)
# ===========================================================================
echo "[pkos-audit] 8/12 scheduled jobs" >&2
{
  printf '{'
  printf '"_why_this_matters":"every scheduled mechanism must be surfaced with its exact command line - an unattended job previously consumed an entire LLM subscription",'
  printf '"root_crontab":%s,' "$(capture_sh 15 'root crontab' "crontab -l -u root 2>/dev/null || echo 'unavailable: cannot read root crontab (need root)'")"
  printf '"all_user_crontabs":%s,' "$(capture_sh 20 'per-user crontabs' \
     "if [ \$(id -u) -eq 0 ]; then cut -d: -f1 /etc/passwd | while read -r u; do c=\$(crontab -l -u \"\$u\" 2>/dev/null); [ -n \"\$c\" ] && echo \"=== \$u ===\" && echo \"\$c\"; done; else echo 'REQUIRES_ROOT'; fi")"
  printf '"etc_crontab":%s,' "$(capture - cat /etc/crontab)"
  printf '"cron_d":%s,' "$(capture_sh 15 'cron.d + cron.* dirs' \
     "for d in /etc/cron.d /etc/cron.hourly /etc/cron.daily /etc/cron.weekly /etc/cron.monthly; do [ -d \"\$d\" ] && ls -la \"\$d\" 2>/dev/null | sed \"s|^|\$d: |\"; done; echo '--- cron.d contents ---'; grep -rH '' /etc/cron.d/ 2>/dev/null | head -100")"
  printf '"systemd_timers":%s,' "$(capture systemctl systemctl list-timers --all --no-pager --no-legend)"
  printf '"systemd_user_timers":%s,' "$(capture_sh 15 'user timers' "systemctl --user list-timers --all --no-pager --no-legend 2>/dev/null || echo 'unavailable'")"
  printf '"at_jobs":%s,' "$(capture atq atq)"
  printf '"pm2_cron_restarts":%s' "$(capture_sh 20 'pm2 cron_restart settings' \
     "if command -v pm2 >/dev/null 2>&1; then pm2 jlist 2>/dev/null | tr ',' '\\n' | grep -i 'cron_restart\|\"name\"' | head -60; else echo 'unavailable: pm2 not installed'; fi")"
  printf '}'
} > "$TMPD/scheduled"; add_section scheduled "$(cat "$TMPD/scheduled")"

# ===========================================================================
# 9. AGE PROFILE  (SOW 49 - evidence for old-data classification)
# ===========================================================================
echo "[pkos-audit] 9/12 age profile" >&2
{
  printf '{'
  printf '"_warning":"age alone is NEVER sufficient justification for deletion (SOW 49). These buckets are evidence for classification, not a delete list.",'
  printf '"buckets":%s,' "$(capture_sh "$TMO_LONG" 'file age buckets' \
     "for d in /root /home /opt /srv /var/log /var/backups; do
        [ -d \"\$d\" ] || continue
        for spec in '0-30d:-mtime -30' '30-180d:-mtime +30 -mtime -180' '180-365d:-mtime +180 -mtime -365' '1-2y:-mtime +365 -mtime -730' '2y+:-mtime +730'; do
          lbl=\${spec%%:*}; expr=\${spec#*:}
          res=\$(timeout 20 find \"\$d\" -xdev -type f \$expr -printf '%s\\n' 2>/dev/null | awk '{n++; b+=\$1} END {printf \"%d %d\", n+0, b+0}')
          echo \"\$d \$lbl \$res\"
        done
      done")"
  printf '"never_accessed_90d_large":%s' "$(capture_sh "$TMO_LONG" 'large files not accessed in 90d' \
     "find /root /home /opt /srv -xdev -type f -size +20M -atime +90 -printf '%s\t%TY-%Tm-%Td\t%AY-%Am-%Ad\t%p\n' 2>/dev/null | sort -rn | head -40")"
  printf '}'
} > "$TMPD/age"; add_section age_profile "$(cat "$TMPD/age")"

# ===========================================================================
# 10. BACKUPS  (paths and tool presence only - NEVER credentials or repo keys)
# ===========================================================================
echo "[pkos-audit] 10/12 backups" >&2
{
  printf '{'
  printf '"_policy":"tool presence and paths only. Repository passwords, keys and env files are NEVER read (SOW 28).",'
  printf '"tools_present":%s,' "$(capture_sh 15 'backup tool presence' \
     "for t in restic borg borgmatic duplicity rclone rsnapshot bacula-fd zfs pg_dump mysqldump; do if command -v \$t >/dev/null 2>&1; then echo \"PRESENT: \$t (\$(command -v \$t))\"; fi; done")"
  printf '"backup_dirs":%s,' "$(capture_sh 30 'candidate backup dirs' \
     "for d in /backup /backups /var/backups /root/backup /root/backups /opt/backup /srv/backup /mnt/backup; do [ -d \"\$d\" ] && timeout 15 du -sh \"\$d\" 2>/dev/null && ls -lat \"\$d\" 2>/dev/null | head -12; done")"
  printf '"backup_configs_present":%s,' "$(capture_sh 20 'backup config FILENAMES only' \
     "find /etc /root /opt -maxdepth 4 \( -iname '*borgmatic*' -o -iname 'restic*' -o -iname 'rclone.conf' -o -iname '*backup*.sh' -o -iname '*backup*.service' -o -iname '*backup*.timer' \) -printf '%TY-%Tm-%Td %p\n' 2>/dev/null | head -40")"
  printf '"zfs_snapshots":%s,' "$(capture zfs zfs list -t snapshot -o name,used,creation)"
  printf '"most_recent_backup_artifacts":%s' "$(capture_sh 40 'newest backup-looking files' \
     "find / -xdev \( -path /proc -o -path /sys -o -path /var/lib/docker \) -prune -o -type f \( -iname '*.dump' -o -iname '*.sql.gz' -o -iname '*backup*.tar.gz' -o -iname '*.borg' \) -printf '%TY-%Tm-%Td %s %p\n' -print0 2>/dev/null | tr -d '\\000' | sort -r | head -30")"
  printf '}'
} > "$TMPD/backups"; add_section backups "$(cat "$TMPD/backups")"

# ===========================================================================
# 11. SECURITY SURFACE  (directives and filenames ONLY - never secret values)
# ===========================================================================
echo "[pkos-audit] 11/12 security surface" >&2
{
  printf '{'
  printf '"_policy":"REDACTION GUARD: this section reads specific sshd directives and lists FILENAMES. It never prints the contents of any key, .env, token or password file.",'
  printf '"sshd_directives":%s,' "$(capture_sh 15 'sshd_config selected directives' \
     "grep -Ei '^[[:space:]]*(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|PermitEmptyPasswords|Port|AllowUsers|AllowGroups|X11Forwarding)' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null || echo 'unavailable: cannot read sshd_config'")"
  printf '"ufw_status":%s,' "$(capture ufw ufw status verbose)"
  printf '"iptables_rule_count":%s,' "$(capture_sh 15 'iptables rule counts' \
     "if command -v iptables >/dev/null 2>&1; then iptables -S 2>/dev/null | wc -l | sed 's/^/iptables_rules: /'; iptables -t nat -S 2>/dev/null | wc -l | sed 's/^/nat_rules: /'; else echo 'unavailable: iptables not installed'; fi")"
  printf '"fail2ban":%s,' "$(capture_sh 15 'fail2ban status' "if command -v fail2ban-client >/dev/null 2>&1; then fail2ban-client status 2>/dev/null; else echo 'unavailable: fail2ban not installed'; fi")"
  printf '"users_with_shells":%s,' "$(capture_sh 10 'login-capable users' "awk -F: '\$7 !~ /(nologin|false|sync)\$/ {print \$1\" uid=\"\$3\" shell=\"\$7}' /etc/passwd 2>/dev/null")"
  printf '"sudoers_files":%s,' "$(capture_sh 10 'sudoers FILENAMES only' "ls -la /etc/sudoers.d/ 2>/dev/null; echo '(filenames only - contents deliberately not read)'")"
  printf '"authorized_keys_counts":%s,' "$(capture_sh 15 'authorized_keys line counts (no key material)' \
     "for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do [ -f \"\$f\" ] && echo \"\$f: \$(wc -l < \"\$f\" 2>/dev/null) key(s)\"; done")"
  printf '"credential_files_present":%s,' "$(capture_sh 25 'credential file NAMES only - contents never read' \
     "find /root /home /opt /srv -maxdepth 4 \( -name '.env' -o -name '*.pem' -o -name 'id_rsa' -o -name 'id_ed25519' -o -name 'credentials' -o -name '*.key' \) -printf '%TY-%Tm-%Td %p\n' 2>/dev/null | head -60")"
  printf '"listening_public":%s' "$(capture_sh 15 'sockets bound to 0.0.0.0 or ::' "ss -tulpn 2>/dev/null | grep -E '0\.0\.0\.0:|\[::\]:' | head -40")"
  printf '}'
} > "$TMPD/security"; add_section security_surface "$(cat "$TMPD/security")"

# ===========================================================================
# 12. PKOS-SPECIFIC PROBES  (does a second brain already exist here?)
# ===========================================================================
echo "[pkos-audit] 12/12 pkos probes" >&2
{
  printf '{'
  printf '"obsidian_vaults":%s,' "$(capture_sh 25 'obsidian vaults' "find /root /home /opt /srv -maxdepth 5 -type d -name '.obsidian' -printf '%p\n' 2>/dev/null | head -20")"
  printf '"git_repos":%s,' "$(capture_sh 30 'git repos' "find /root /home /opt /srv -maxdepth 5 -type d -name '.git' -printf '%p\n' 2>/dev/null | head -60")"
  printf '"vector_stores":%s,' "$(capture_sh 25 'vector/search store dirs' \
     "for d in /var/lib/qdrant /var/lib/elasticsearch /var/lib/opensearch /opt/qdrant /opt/chroma /root/.chroma; do [ -d \"\$d\" ] && timeout 10 du -sh \"\$d\" 2>/dev/null; done; echo '--- containers ---'; command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -Ei 'qdrant|weaviate|milvus|chroma|elastic|opensearch|neo4j|typesense|meili' || true")"
  printf '"n8n_present":%s,' "$(capture_sh 15 'n8n' "command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}' 2>/dev/null | grep -i n8n || echo 'none found'")"
  printf '"hermes_present":%s,' "$(capture_sh 15 'hermes agent' "for d in /root/.hermes /home/*/.hermes; do [ -d \"\$d\" ] && echo \"PRESENT: \$d\" && ls -1 \"\$d\" 2>/dev/null | head -10; done; command -v hermes >/dev/null 2>&1 && echo 'hermes binary on PATH'")"
  printf '"python_env":%s' "$(capture_sh 15 'python' "python3 --version 2>/dev/null; pip3 --version 2>/dev/null | head -1")"
  printf '}'
} > "$TMPD/pkos"; add_section pkos_probes "$(cat "$TMPD/pkos")"

# ===========================================================================
# ASSEMBLE
# ===========================================================================
add_note "STRICTLY READ-ONLY audit. Nothing on this system was created, modified or deleted."
add_note "No network calls were made."
add_note "Sections marked TIMEOUT/unavailable/REQUIRES_ROOT are recorded in 'errors' - a missing section is never silently omitted (SOW 43)."
add_note "Age buckets are classification evidence only. Age alone never justifies deletion (SOW 49)."
add_note "Docker and archive sections are INVENTORY ONLY. No prune, no extraction."
add_note "Secret values were never read. Only filenames and specific config directives."

{
  printf '{'
  printf '"schema_version":"%s",' "$SCHEMA_VERSION"
  printf '"generated_at_utc":"%s",' "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
  printf '"generator":"pkos-server-audit.sh",'
  printf '"host":"%s",' "$(jesc "$HOST")"
  printf '"ran_as_root":%s,' "$([ $IS_ROOT -eq 1 ] && echo true || echo false)"
  printf '"notes":[%s],' "$(join_by , "${NOTES[@]}")"
  printf '%s,' "$(join_by , "${SECTIONS[@]}")"
  printf '"error_count":%s,' "$(wc -l < "$ERRLOG" 2>/dev/null || echo 0)"
  printf '"errors":['
  awk 'NR>1{printf ","} {printf "%s", $0}' "$ERRLOG" 2>/dev/null
  printf ']' 
  printf '}'
  printf '\n'
} > "$OUT"

echo "[pkos-audit] DONE" >&2
echo "[pkos-audit] report: $OUT" >&2
echo "[pkos-audit] size:   $(wc -c < "$OUT" 2>/dev/null) bytes" >&2
echo "[pkos-audit] issues: $(wc -l < "$ERRLOG" 2>/dev/null || echo 0) recorded in .errors" >&2
echo "" >&2
echo "Next: copy this file back to your laptop, into" >&2
echo "  AutoMSP BOS Claude Project\\pkos\\90-evidence\\servers\\" >&2
