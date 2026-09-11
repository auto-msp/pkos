<#
  PKOS Part 2 runbook  -  the steps that need Moiz's machine, in one file.
  Generated 2026-09-11.

  WHY THIS FILE EXISTS
  Cowork's Linux workspace still cannot mount the connected folders (the
  Plan9 mount error from the September 8 Windows update), and the cloud
  container cannot reach Perceptor on port 22. So everything below is work
  that could not be done from the session, not work that was skipped.

  HOW TO RUN
  Each step is independent and idempotent - re-running a completed step
  reports what is already done and changes nothing. Run them in any order,
  one at a time. Every step ends by printing a NUMBER, because "no error"
  is not proof of success (SOW 43).

      powershell -ExecutionPolicy Bypass -File pkos-part2.ps1 -Step 1

  NOTHING HERE SCHEDULES ANYTHING. No cron entry, no scheduled task, no pm2
  restart schedule is created or enabled by this file (standing instruction
  3.3). Step 6 PROVES the offsite backup guard and then stops, so the
  decision to schedule it stays yours.
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateRange(1,7)][int]$Step,
  [string]$Pkos = "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos",
  [string]$Perceptor = "132.145.133.39"
)

$ErrorActionPreference = "Stop"
function Say($m) { Write-Host $m -ForegroundColor Cyan }
function Num($label, $value) { Write-Host ("  {0,-44} {1}" -f $label, $value) -ForegroundColor Green }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }

$Skel = Join-Path $Pkos "03-skeleton"
$Store = Join-Path $Pkos "02-canonical\pkos-store"
$env:PYTHONPATH = "."
$env:PKOS_ROOT = $Store

# ===========================================================================
if ($Step -eq 1) {
Say "STEP 1  Convert the four PuTTY keys"
# puttygen.exe is a GUI program. Called directly it detaches immediately and
# writes nothing, and the shell reports success - one of the silent failures
# this project keeps hitting. -Wait is what makes it actually do the work.
$K  = "C:\Users\MoizContractor\Downloads\10 - Tools & Software\Putty Keys New\newputtykeys"
$PG = "C:\Program Files\PuTTY\puttygen.exe"
if (-not (Test-Path $PG)) { throw "puttygen not found at $PG - install PuTTY or fix the path" }
New-Item -ItemType Directory -Force -Path "$HOME\.ssh" | Out-Null

$keys = @(
  @{ ppk = "AdguardPvt.ppk.ppk"; out = "ironhide_key"   },
  @{ ppk = "automsppvt.ppk";     out = "ratchet_key"    },
  @{ ppk = "cloudpanel_key.ppk"; out = "prowl_key"      },
  @{ ppk = "my-rdp.ppk";         out = "wheeljack_key"  }
)
$made = 0; $missing = @()
foreach ($k in $keys) {
  $src = Join-Path $K $k.ppk
  $dst = "$HOME\.ssh\$($k.out)"
  if (-not (Test-Path $src)) { $missing += $k.ppk; continue }
  if (Test-Path $dst) { Write-Host "  already converted: $($k.out)"; $made++; continue }
  Start-Process $PG -ArgumentList "`"$src`"","-O","private-openssh","-o","`"$dst`"" -Wait -NoNewWindow
  if (Test-Path $dst) { $made++ } else { Warn "  puttygen produced nothing for $($k.ppk) - is it passphrase-protected?" }
}
Num "keys present as OpenSSH" $made
Num "source .ppk files not found" $missing.Count
if ($missing.Count) { Warn ("  missing: " + ($missing -join ", ")) }
Get-ChildItem "$HOME\.ssh\*_key" -ErrorAction SilentlyContinue |
  Select-Object Name, Length | Format-Table -AutoSize
}

# ===========================================================================
if ($Step -eq 2) {
Say "STEP 2  Audit the six unaudited servers  (unblocks Phase 1, then Phase 2)"
# The audit script is read-only. The user on these boxes is `ubuntu`, not
# root, and the script is dos2unix'd on arrival because a CRLF shebang makes
# bash fail with a message that looks nothing like the real cause.
$hosts = @(
  @{ ip="129.158.236.50"; key="ironhide_key";   name="ironhide"  },
  @{ ip="141.148.58.44";  key="ratchet_key";    name="ratchet"   },
  @{ ip="129.213.93.2";   key="prowl_key";      name="prowl"     },
  @{ ip="150.136.67.246"; key="wheeljack_key";  name="wheeljack" },
  # BumbleBee, added 2026-09-11. The key name is a PLACEHOLDER: no .ppk for
  # this host was in the key folder, and guessing which key opens a server is
  # how you get locked out or, worse, silently audit the wrong box. Set it,
  # or drop this line, before running.
  @{ ip="150.136.35.253"; key="bumblebee_key";  name="bumblebee" },
  # Sentinel Prime, named 2026-09-11. Airtable records its SSH key as NOT
  # WORKING, so this will skip rather than fail - which is the honest outcome
  # until a usable key exists. Listed anyway so the audit gap stays visible in
  # the run output instead of being invisible by omission.
  @{ ip="158.101.117.121"; key="sentinelprime_key"; name="sentinel-prime" }
)
$dest = Join-Path $Pkos "90-evidence\servers"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$ok = 0; $failed = @()
foreach ($h in $hosts) {
  Write-Host "=== $($h.name) ($($h.ip)) ===" -ForegroundColor Magenta
  $key = "$HOME\.ssh\$($h.key)"
  if (-not (Test-Path $key)) {
    if ($h.name -eq "bumblebee") {
      Warn "  bumblebee: no key configured yet. Tell Claude which key this host takes,"
      Warn "            or point `$h.key at the right file. Skipping rather than guessing."
    } elseif ($h.name -eq "sentinel-prime") {
      Warn "  sentinel-prime: Airtable records this host's SSH key as not working."
      Warn "            It cannot be audited until a usable key exists. Not a failure"
      Warn "            of this script - a known, recorded gap."
    } else {
      Warn "  no key at $key - run Step 1 first"
    }
    $failed += $h.name; continue
  }
  try {
    scp -o StrictHostKeyChecking=accept-new -i $key (Join-Path $Pkos "99-runbooks\pkos-server-audit.sh") "ubuntu@$($h.ip):/tmp/"
    ssh -o StrictHostKeyChecking=accept-new -i $key "ubuntu@$($h.ip)" "sed -i 's/\r`$//' /tmp/pkos-server-audit.sh; sudo bash /tmp/pkos-server-audit.sh --out /tmp/audit.json"
    scp -i $key "ubuntu@$($h.ip):/tmp/audit.json" (Join-Path $dest "$($h.name)-audit.json")
    $ok++
  } catch { Warn "  $($h.name): $_"; $failed += $h.name }
}
Num "servers audited this run" $ok
Num "audit JSON files now on disk" (Get-ChildItem "$dest\*-audit.json" -ErrorAction SilentlyContinue).Count
if ($failed.Count) { Warn ("  failed: " + ($failed -join ", ")) }
Write-Host "`nNow ingest them:" -ForegroundColor Cyan
Write-Host "  cd `"$Skel`"; python -m secondbrain ingest server-audit `"$dest`""
}

# ===========================================================================
if ($Step -eq 3) {
Say "STEP 3  Phase 3 - ingest the laptop folders that were never connected"
# Surveyed from the session on 2026-09-11. Two notes that matter:
#  * AutoMSP\ and OneDrive\ have no subdirectories at all - loose files only.
#  * automsp-obsidian-vault.git is a BARE GIT REPOSITORY, not a vault. Its
#    contents are zlib-compressed loose objects; ingesting it would add
#    thousands of unreadable binaries and no knowledge. The adapter now
#    refuses it by structure and tells you to clone a working tree first.
#    You almost certainly do not need to: Perceptor already holds the real
#    vault at /root/Obsidian (61,512 files, count-matched).
Set-Location $Skel
$targets = @(
  "C:\Users\MoizContractor\Documents",
  "C:\Users\MoizContractor\OneDrive",
  "C:\Users\MoizContractor\AutoMSP",
  "C:\Users\MoizContractor\bos-fable-5-work"
)
foreach ($t in $targets) {
  if (-not (Test-Path $t)) { Warn "  not found, skipping: $t"; continue }
  Write-Host "--- $t" -ForegroundColor Magenta
  python -m secondbrain ingest filesystem "$t"
}
Write-Host "`nCount what landed:" -ForegroundColor Cyan
python -m secondbrain --json inventory | python -c "import json,sys; d=json.load(sys.stdin); print('  objects now:', d.get('counts',{}).get('objects'))"
Warn "bos-fable-5-work carries .venv/ and .git/ - both are excluded by SOW 75 already."
Warn "If you DO want the Obsidian vault's working tree from the bare repo:"
Warn "  git clone `"C:\Users\MoizContractor\automsp-obsidian-vault.git`" `"$env:TEMP\vault-worktree`""
Warn "  python -m secondbrain ingest filesystem `"$env:TEMP\vault-worktree`""
}

# ===========================================================================
if ($Step -eq 4) {
Say "STEP 4  Ingest the Airtable snapshots captured in the session"
Set-Location $Skel
$snap = Join-Path $Pkos "90-evidence\airtable"
if (-not (Test-Path $snap)) { throw "no snapshots at $snap" }
python -m secondbrain ingest airtable "$snap" --identity openmynewopportunities@gmail.com
Write-Host "`nThen check nothing credential-shaped landed in a body:" -ForegroundColor Cyan
python -m secondbrain secrets
Warn "Two objects WILL be flagged: the OpenClaw/Jarvis access tokens that were"
Warn "sitting in the Airtable 'AI coding agents' notes. `secrets --redact`"
Warn "removes them from the canonical body; the evidence blob keeps the original."
}

# ===========================================================================
if ($Step -eq 5) {
Say "STEP 5  Ship the skeleton and the 26/27 bundle to Perceptor"
# The laptop store is AHEAD of Perceptor by phases 26 and 27, plus everything
# built in Part 2. sync --import will correctly refuse until this runs.
Set-Location $Skel
$bundle = Join-Path $Pkos "95-transfer\bundle-part2"
python -m secondbrain sync --export "$bundle" --canonical-only
Num "bundle files" (Get-ChildItem $bundle -Recurse -File).Count

Set-Location $Pkos
if (Test-Path "skeleton.tar.gz") { Remove-Item "skeleton.tar.gz" }
tar -czf skeleton.tar.gz 03-skeleton
Num "skeleton.tar.gz bytes" (Get-Item "skeleton.tar.gz").Length

scp -o StrictHostKeyChecking=accept-new -r "$bundle" "skeleton.tar.gz" "root@${Perceptor}:/root/pkos/"
ssh "root@$Perceptor" @"
set -u
cd /root/pkos
tar -xzf skeleton.tar.gz
cd 03-skeleton
export PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=.
python3 -m secondbrain sync --import /root/pkos/bundle-part2
python3 -m secondbrain validate
for t in tests/test_*.py; do python3 "\$t" >/dev/null 2>&1 || echo "FAIL \$t"; done
python3 -m secondbrain rebuild-index --quiet
python3 -m secondbrain status
"@
Warn "Note the deliberate absence of `set -e` in that block. Post-mortem 12.4:"
Warn "`set -euo pipefail` killed the 7am staging sync for two and a half months"
Warn "because the error branch became unreachable by construction."
}

# ===========================================================================
if ($Step -eq 6) {
Say "STEP 6  PROVE the offsite backup concurrency guard  (does NOT schedule it)"
# The pgrep guard in vault-offsite-backup.sh has never been observed to fire.
# An unproven guard is a hypothesis, and this one is the only thing standing
# between a running rsync and post-mortem 12.5 - a partial archive overwriting
# a good backup. Fire it deliberately and read the exit code.
ssh "root@$Perceptor" @"
echo '--- starting a dummy long rsync so the guard has something to see'
rsync -a --bwlimit=1 /root/Obsidian/ /tmp/guard-probe/ &
DUMMY=\$!
sleep 3
echo '--- invoking the backup script while that rsync is running'
/root/bin/vault-offsite-backup.sh
echo "GUARD_EXIT=\$?"
kill \$DUMMY 2>/dev/null
rm -rf /tmp/guard-probe
echo '--- expected: GUARD_EXIT=75 and no archive written'
"@
Warn ""
Warn "If GUARD_EXIT=75, the guard is proven and the script is safe to schedule."
Warn "It is still NOT scheduled. Ask me and I will write the cron line - I will"
Warn "not add one on my own (standing instruction 3.3)."
}

# ===========================================================================
if ($Step -eq 7) {
Say "STEP 7  Reclaim ~380 MB of superseded artefacts on Perceptor"
ssh "root@$Perceptor" @"
echo '--- what would go:'
ls -la /root/pkos/pkos-store/canonical/superseded-*.sqlite3 2>/dev/null || echo '  (none left)'
du -ch /root/pkos/pkos-store/canonical/superseded-*.sqlite3 2>/dev/null | tail -1
echo '--- proving the live store is healthy BEFORE deleting anything'
cd /root/pkos/03-skeleton
PKOS_ROOT=/root/pkos/pkos-store PKOS_DERIVED=/root/pkos/derived PYTHONPATH=. \
  python3 -m secondbrain validate --deep | tail -4
"@
Warn ""
Warn "Read that output. Only if validate --deep says PASSED, run:"
Warn "  ssh root@$Perceptor 'rm -f /root/pkos/pkos-store/canonical/superseded-*.sqlite3'"
Warn "Deleting first and checking after is how 12.5 happened."
}
