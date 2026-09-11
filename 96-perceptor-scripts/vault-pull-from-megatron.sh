#!/bin/bash
# Keep Perceptor's vault replica current, pulled FROM Megatron.
#
# This exists only until the cutover. Until then Megatron holds the two live
# writers (the Obsidian desktop app and n8n), so Perceptor must be a strict
# replica: it pulls, it never pushes back. The day the cutover happens this
# script is disabled FIRST, before anything on Perceptor is allowed to write.
#
# --delete is deliberately absent. A replica that mirrors deletions will
# faithfully replicate an accident. Space is cheaper than a lost note.
set -uo pipefail
SRC="root@100.80.47.37:/root/Obsidian/"
DST="/root/Obsidian/"
KEY="/root/.ssh/fleet_ed25519"
LOG="/var/log/vault-pull.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

if [ -f /root/.vault-cutover-done ]; then
    log "cutover marker present - Perceptor is authoritative, refusing to pull"
    exit 0
fi

log "=== PULL STARTED ==="
if OUT=$(rsync -aH --stats -e "ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=20" \
         "$SRC" "$DST" 2>&1); then
    log "ok: $(echo "$OUT" | grep -E 'Number of regular files transferred|Total file size' | tr '\n' ' ')"
    log "=== PULL COMPLETED ==="
else
    log "FAILED: $(echo "$OUT" | tail -4 | tr '\n' ' ')"
    log "=== PULL FAILED ==="
    exit 1
fi
