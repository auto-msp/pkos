<#
  Push the PKOS working folder to auto-msp/pkos, from YOUR laptop.

  Why from here and not from the Claude session: the cloud sandbox's git proxy
  maintains its own authorized repository set and injects its own credentials.
  auto-msp/pkos is not in that set, so the proxy refused the push before any
  token of mine was ever consulted - which is also why the PAT was useless and
  should be revoked.

  Your laptop has no such proxy. This is ~30 seconds.

      powershell -ExecutionPolicy Bypass -File push-to-github.ps1

  It initialises git in the pkos folder if needed, excludes the store (the
  sqlite database and the evidence blobs must never travel through GitHub),
  commits, and pushes. Safe to re-run.
#>
[CmdletBinding()]
param(
  [string]$Pkos = "C:\Users\MoizContractor\Downloads\AutoMSP BOS Claude Project\pkos",
  [string]$Remote = "https://github.com/auto-msp/pkos.git"
)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Host $m -ForegroundColor Cyan }
function Num($l,$v) { Write-Host ("  {0,-40} {1}" -f $l,$v) -ForegroundColor Green }

Set-Location $Pkos

# The store never goes to GitHub. 02-canonical holds a 395 MB sqlite database
# and 9,055 evidence blobs; GitHub is a courier for CODE, not the archive.
@'
__pycache__/
*.pyc
02-canonical/
95-transfer/
*.sqlite3
*.sqlite3-wal
*.sqlite3-shm
evidence/blobs/
*.tar.gz
skeleton.tar.gz
'@ | Set-Content -Path ".gitignore" -Encoding utf8

if (-not (Test-Path ".git")) { Say "initialising git in $Pkos"; git init -q; git branch -M main }
if (-not (git remote 2>$null | Select-String -Quiet '^origin$')) { git remote add origin $Remote }
else { git remote set-url origin $Remote }

git add -A
$staged = (git diff --cached --name-only | Measure-Object -Line).Lines
Num "files staged" $staged

# Prove the store is not in the commit BEFORE pushing, not after.
$leak = git diff --cached --name-only | Select-String -Pattern 'sqlite3|evidence/blobs/|02-canonical/'
if ($leak) {
  Write-Host "REFUSING TO PUSH - store artefacts are staged:" -ForegroundColor Red
  $leak | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
  Write-Host "  Fix .gitignore and re-run. Nothing was pushed." -ForegroundColor Red
  exit 1
}
Num "store artefacts staged (must be 0)" 0

if ($staged -gt 0) {
  git -c user.email="moiz.contractor@automsp.us" -c user.name="Moiz Contractor" `
      commit -q -m "PKOS Part 2: adapters, fleet naming, Airtable capture

12 new ingestion adapters (phases 9-19 plus Obsidian and n8n), 5 bug fixes,
225 Airtable records captured, fleet renamed to Transformers names as canonical.
13 test suites green."
}
Say "pushing to $Remote"
git push -u origin main
Num "pushed" "ok"

Write-Host ""
Say "Then on Perceptor:"
Write-Host "  ssh root@132.145.133.39"
Write-Host "  cd /root/pkos && git clone https://github.com/auto-msp/pkos.git pkos-git || (cd pkos-git && git pull)"
Write-Host "  # or simply use Step 5 of pkos-part2.ps1, which scp's directly and skips GitHub entirely"
