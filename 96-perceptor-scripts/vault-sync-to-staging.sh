#!/bin/bash
# AutoMSP BOS — vault → staging (Ratchet, 141.148.58.44), run FROM PERCEPTOR.
#
# WHY THIS IS A REWRITE, NOT A COPY
# The original ran `set -euo pipefail` and then did:
#       RSYNC_OUTPUT=$(rsync ...)
#       RSYNC_EXIT=$?
#       if [ $RSYNC_EXIT -ne 0 ]; then log "ERROR: ..."; fi
# Under `set -e` a failing command substitution kills the shell AT THE
# ASSIGNMENT. `RSYNC_EXIT=$?` is never reached and the error branch can never
# run. The log therefore ends mid-sentence at "Step 1: Syncing vault files..."
# and says nothing at all about the failure.
#
# That is exactly what happened: last successful run 2026-06-25, silent daily
# failure every day since, discovered 2026-09-08. An error handler that cannot
# execute is worse than no error handler, because it looks like one.
#
# Root cause of the failure itself: Megatron egresses from 96.45.71.2 and
# Ratchet does not accept connections from it. Perceptor can reach Ratchet,
# which is why this script now lives here.
set -uo pipefail          # NOT -e: every step must be able to report itself

LOGFILE="/root/Obsidian/vault/app/logs/staging-sync.log"
SSH_KEY="/root/.ssh/fleet_ed25519"
SSH_OPTS="-o ConnectTimeout=30 -o BatchMode=yes"
SOURCE="/root/Obsidian/vault/"
TARGET="root@141.148.58.44:/root/Obsidian/vault/"
PM2_TARGET="root@141.148.58.44"
FAILED=0

mkdir -p "$(dirname "$LOGFILE")"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOGFILE"; }
step() { log "--- $* ---"; }

log "=== STAGING SYNC STARTED (from $(hostname)) ==="

step "reachability"
if ! ssh $SSH_OPTS -i "$SSH_KEY" "$PM2_TARGET" true 2>/dev/null; then
    log "ABORT: cannot reach $PM2_TARGET over ssh. Nothing was changed."
    log "=== STAGING SYNC FAILED (unreachable) ==="
    exit 1
fi

step "step 1: vault files"
if OUT=$(rsync -avz --delete \
        --exclude='app/node_modules/' --exclude='app/.next/' \
        --exclude='app/logs/' --exclude='.git/' \
        --exclude='app/.tsbuildinfo' --exclude='app/tsconfig.tsbuildinfo' \
        -e "ssh $SSH_OPTS -i $SSH_KEY" "$SOURCE" "$TARGET" 2>&1); then
    log "ok: $(echo "$OUT" | tail -2 | tr '\n' ' ')"
else
    rc_rsync=$?            # MUST be the first statement: any command here
    FAILED=1               # (even an assignment) overwrites $?
    log "FAILED (rsync exit $rc_rsync): $(echo "$OUT" | tail -5 | tr '\n' ' ')"
    log "=== STAGING SYNC FAILED at step 1 ==="
    exit 1                      # no point deploying a vault that did not arrive
fi

step "step 2: .next build"
if OUT=$(rsync -avz -e "ssh $SSH_OPTS -i $SSH_KEY" \
        /root/Obsidian/vault/app/.next/ \
        "root@141.148.58.44:/root/Obsidian/vault/app/.next/" 2>&1); then
    log "ok: $(echo "$OUT" | tail -2 | tr '\n' ' ')"
else
    FAILED=1; log "FAILED: $(echo "$OUT" | tail -3 | tr '\n' ' ')"
fi

step "step 3: dependencies"
OUT=$(ssh $SSH_OPTS -i "$SSH_KEY" "$PM2_TARGET" \
      'cd /root/Obsidian/vault/app && npm install --production 2>&1 | tail -3')
log "npm: $OUT"

step "step 4: restart"
OUT=$(ssh $SSH_OPTS -i "$SSH_KEY" "$PM2_TARGET" 'pm2 restart automsp-staging 2>&1 | tail -3')
log "pm2: $OUT"

step "step 5: health"
sleep 5
HEALTH=$(ssh $SSH_OPTS -i "$SSH_KEY" "$PM2_TARGET" \
         'curl -s -o /dev/null -w "%{http_code}" http://localhost:3100/ 2>/dev/null')
log "health: HTTP ${HEALTH:-no-response}"
[ "$HEALTH" = "200" ] || FAILED=1

# keep the log bounded
if [ -f "$LOGFILE" ] && [ "$(stat -c%s "$LOGFILE" 2>/dev/null || echo 0)" -gt 10485760 ]; then
    tail -2000 "$LOGFILE" > "$LOGFILE.tmp" && mv "$LOGFILE.tmp" "$LOGFILE"
    log "log rotated"
fi

if [ "$FAILED" -eq 0 ]; then
    log "=== STAGING SYNC COMPLETED SUCCESSFULLY ==="
    exit 0
fi
log "=== STAGING SYNC COMPLETED WITH FAILURES ==="
exit 1
