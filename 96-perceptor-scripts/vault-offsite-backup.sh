#!/bin/bash
# AutoMSP vault → off-site (Google Drive), run FROM PERCEPTOR.
# Replaces the 02:00 crontab one-liner removed on 2026-09-08.
#
# WHY THIS IS A REWRITE
# The original was four operations chained with &&:
#     tar && rclone copy && rsync-to-ratchet && find /tmp -delete
# The rsync leg had been failing since June, so the cleanup after it NEVER ran
# and 796 MB of daily tarballs silently accumulated in /tmp. A chain of && is a
# fine way to express "stop on error"; it is a terrible way to express "do four
# unrelated things". Each leg here runs and reports on its own.
set -uo pipefail

VAULT_PARENT="/root/Obsidian"
STAGE="/root/backups/vault"          # NOT /tmp - systemd-tmpfiles wipes /tmp
REMOTE="gdrive:AutoMSP-Backups/"
KEEP_DAYS=3
LOG="/var/log/vault-offsite-backup.log"
STAMP=$(date +%Y%m%d)
HOST=$(hostname -s)
# The archive name carries the HOST. Without it, every machine that backs up
# this vault writes to gdrive:AutoMSP-Backups/automsp-vault-backup-YYYYMMDD.tar.gz
# - the same object - and the last one to run silently overwrites the others.
# That happened on 2026-09-08: a partial archive from this host replaced
# Megatron's complete one for the same date. An upload that destroys another
# machine's backup is not a backup.
ARCHIVE="$STAGE/automsp-vault-backup-$HOST-$STAMP.tar.gz"
rc=0

mkdir -p "$STAGE"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }
log "=== OFF-SITE BACKUP STARTED on $(hostname) ==="

# Refuse to archive a directory something else is actively writing into.
# A tar taken mid-rsync is a mixture of two states, and it looks completely
# normal: right name, plausible size, exit code 0.
if pgrep -f "rsync.*$VAULT_PARENT" >/dev/null 2>&1; then
    log "ABORT: an rsync is writing into $VAULT_PARENT right now."
    log "Archiving mid-sync produces a silently mixed snapshot. Nothing was written."
    log "=== OFF-SITE BACKUP SKIPPED ==="
    exit 75          # EX_TEMPFAIL - retry later, this is not a real failure
fi
if [ -f "$VAULT_PARENT/../.vault-sync-in-progress" ]; then
    log "ABORT: sync-in-progress marker present. Nothing was written."
    log "=== OFF-SITE BACKUP SKIPPED ==="
    exit 75
fi

# 1. archive
if tar -czf "$ARCHIVE" -C "$VAULT_PARENT" \
        --exclude='vault/app/node_modules' --exclude='vault/app/.next' \
        --exclude='vault/app/.git' vault 2>>"$LOG"; then
    log "archive ok: $(du -h "$ARCHIVE" | cut -f1)"
else
    log "ARCHIVE FAILED - nothing to upload"
    log "=== OFF-SITE BACKUP FAILED ==="
    exit 1
fi

# 2. upload - independent of everything after it
if rclone copy "$ARCHIVE" "$REMOTE" 2>>"$LOG"; then
    log "uploaded to $REMOTE"
    # prove it landed rather than trusting a zero exit code
    if rclone lsf "$REMOTE" 2>/dev/null | grep -q "$(basename "$ARCHIVE")"; then
        log "verified present on remote"
    else
        log "WARNING: upload reported success but the file is not listed remotely"
        rc=1
    fi
else
    log "UPLOAD FAILED - the local archive is kept"
    rc=1
fi

# 3. prune - runs whether or not the upload worked, but only ever removes
#    archives older than KEEP_DAYS, and never the one just made
find "$STAGE" -name "automsp-vault-backup-$HOST-*.tar.gz" -mtime "+$KEEP_DAYS" \
     -not -name "$(basename "$ARCHIVE")" -print -delete >> "$LOG" 2>&1

log "local archives: $(ls -1 "$STAGE"/automsp-vault-backup-"$HOST"-*.tar.gz 2>/dev/null | wc -l) using $(du -sh "$STAGE" 2>/dev/null | cut -f1)"
[ "$rc" -eq 0 ] && log "=== OFF-SITE BACKUP COMPLETED ===" || log "=== OFF-SITE BACKUP COMPLETED WITH FAILURES ==="
exit "$rc"
