<#
    Clean-Downloads.ps1  --  PKOS Downloads cleanup
    Generated 2026-09-08. Removes build/dependency folders and software installers.

    WHAT IT DELETES
      * node_modules, .venv, venv, .next, .nuxt, __pycache__, .gradle,
        .pytest_cache, .mypy_cache, .turbo, .parcel-cache
      * QuickBooks / ffmpeg / Goose / InvisibleManXRay distribution folders
      * loose .exe, .msi, .msix, .qcow2 installers

    WHAT IT NEVER TOUCHES
      * your source code (.py .js .ts .java ... ) -- 6,791 files
      * every document, PDF, spreadsheet, image, export
      * "AutoMSP BOS Claude Project" -- the Second Brain lives there
      * anything outside C:\Users\MoizContractor\Downloads

    Every path is verified against those two rules again at delete time.
    Run with -DryRun first if you want to see the list without deleting.
#>
param([switch]$DryRun)

$Root      = 'C:\Users\MoizContractor\Downloads'
$Protected = 'AutoMSP BOS Claude Project'

$Dirs = @(
  'C:\Users\MoizContractor\Downloads\.tmp.drivedownload'
  'C:\Users\MoizContractor\Downloads\.tmp.driveupload'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP App\omnichannel-router\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website Components\AutoMSP Version2\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website Components\fraud-detection-app\.next'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website Components\fraud-detection-app\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website Components\mind-space-saa-s-landing-page-template\.next'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website Components\mind-space-saa-s-landing-page-template\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website Components\neumorphic-user-onboarding\.next'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website Components\neumorphic-user-onboarding\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website(AntiGravity)\AutoMSP\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website(AntiGravity)\backend\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website(BlackBox Ai + GLM 4.7)\automsp-hub\backend\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website(BlackBox Ai + GLM 4.7)\automsp-hub\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website(Cursor + GLM 4.7)\backend\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP Website(Cursor + GLM 4.7)\frontend\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP Website Ver 2.0\automsp-hub-52\node_modules'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\alembic\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\alembic\versions\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\api\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\api\v1\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\core\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\db\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\db\repositories\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\integrations\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\integrations\cooldowns\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\integrations\credentials\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\integrations\hubspot\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\integrations\queue\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\integrations\servicenow\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\ml\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\models\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\processing\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\schemas\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\src\app\services\__pycache__'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\AutoMSP_Business_Canvas\GSD\venv'
  'C:\Users\MoizContractor\Downloads\01 - AutoMSP & CoreIT\AutoMSP\automsp-hub\node_modules'
  'C:\Users\MoizContractor\Downloads\02 - Code Projects\Emily Agent - Livekit Cloud Deployment\livekit-hubspot-integration\node_modules'
  'C:\Users\MoizContractor\Downloads\02 - Code Projects\ai_avatar_it_support_agent-main\ai_avatar_it_support_agent-main\support-agent\__pycache__'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Claude Code\.venv'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Claude Code\__pycache__'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Claude Code\tools\__pycache__'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Cursor - N8N MCP\n8n-mcp\node_modules'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Cursor - N8N MCP\n8n-templates-mcp\node_modules'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\OpenClaw Memory\node_modules'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Voice Agents\Livekit Voice Agent\__pycache__'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Voice Agents\Livekit Voice Agent\livekit-voice-agent\.venv'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Voice Agents\Livekit Voice Agent\livekit-voice-agent\__pycache__'
  'C:\Users\MoizContractor\Downloads\03 - AI Tools & N8N\Voice Agents\PipeCat\Sophia-voice-bot\.venv'
  'C:\Users\MoizContractor\Downloads\04 - Business & Clients\Magical Neer\Website\node_modules'
  'C:\Users\MoizContractor\Downloads\04 - Business & Clients\Websites\Core\apps\backend\node_modules'
  'C:\Users\MoizContractor\Downloads\04 - Business & Clients\Websites\Core\apps\frontend\node_modules'
  'C:\Users\MoizContractor\Downloads\04 - Business & Clients\Websites\Core\node_modules'
  'C:\Users\MoizContractor\Downloads\08 - Learning & Courses\KJ OS Template\AutoMSP AI Brain\03 Projects\(PROJECT TEMPLATE)\.obsidian\plugins\claudian\node_modules'
  'C:\Users\MoizContractor\Downloads\08 - Learning & Courses\KJ OS Template\AutoMSP AI Brain\03 Projects\AutoMSP AI Automation Services\.obsidian\plugins\claudian\node_modules'
  'C:\Users\MoizContractor\Downloads\08 - Learning & Courses\KJ OS Template\AutoMSP AI Brain\claudian\node_modules'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\Goose-Test\SplitClone\auto-msp-expense-tracker-app\android\.gradle'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\Goose-Test\SplitClone\auto-msp-expense-tracker-app\frontend\node_modules'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\Goose-Test\SplitClone\auto-msp-expense-tracker-app\node_modules'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\Goose-Test\SplitClone\node_modules'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\Goose-win32-x64'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\InvisibleManXRay-x64'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\QuickBooks_Enterprise_Solutions_v23.0'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\ffmpeg-2026-04-30-git-cc3ca17127-full_build'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\src\__pycache__'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\src\chatbot\__pycache__'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\src\content\__pycache__'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\src\leads\__pycache__'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\src\scheduling\__pycache__'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\src\shared\__pycache__'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\src\voice\__pycache__'
  'C:\Users\MoizContractor\Downloads\AutoMSP_AI_Consulting_Internship_AllProjects\Project7_SourceCode\tests\__pycache__'
  'C:\Users\MoizContractor\Downloads\outbound\config\__pycache__'
  'C:\Users\MoizContractor\Downloads\outbound\engine\__pycache__'
  'C:\Users\MoizContractor\Downloads\outbound\guardrails\__pycache__'
  'C:\Users\MoizContractor\Downloads\outbound\integrations\__pycache__'
  'C:\Users\MoizContractor\Downloads\outbound\scripts\__pycache__'
  'C:\Users\MoizContractor\Downloads\outbound\tests\__pycache__'
  'C:\Users\MoizContractor\Downloads\outbound\vdd\__pycache__'
)

$Files = @(
  'C:\Users\MoizContractor\Downloads\07 - Data & Exports\Mach5 Data\Telleport - Best Free VPN Installer.exe'
  'C:\Users\MoizContractor\Downloads\07 - Data & Exports\Mach5 Data\TunnelBear-Installer.exe'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\debian-12-genericcloud-arm64.qcow2'
  'C:\Users\MoizContractor\Downloads\10 - Tools & Software\python-manager-26.1.msix'
  'C:\Users\MoizContractor\Downloads\GoogleDriveSetup.exe'
  'C:\Users\MoizContractor\Downloads\Hermes-Setup.exe'
  'C:\Users\MoizContractor\Downloads\Tellnova-1.1.11-win-x64.exe'
  'C:\Users\MoizContractor\Downloads\emBridge.exe'
  'C:\Users\MoizContractor\Downloads\node-v24.20.0-x64.msi'
  'C:\Users\MoizContractor\Downloads\petdex-desktop-win32-x64.exe'
)


function Test-InScope([string]$Path) {
    if (-not $Path.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Warning "REFUSED (outside Downloads): $Path"; return $false }
    if ($Path -like "*$Protected*") {
        Write-Warning "REFUSED (protected - Second Brain): $Path"; return $false }
    return $true
}

$before = (Get-PSDrive C).Free
Write-Host ""
Write-Host "PKOS Downloads cleanup" -ForegroundColor Cyan
Write-Host ("Free space before : {0:N2} GB" -f ($before/1GB))
Write-Host ("Queued            : {0} folders, {1} files" -f $Dirs.Count, $Files.Count)
if ($DryRun) { Write-Host "DRY RUN - nothing will be deleted" -ForegroundColor Yellow }
Write-Host ""

$n = 0; $skipped = 0; $errors = 0
foreach ($d in $Dirs) {
    $n++
    if (-not (Test-InScope $d)) { $skipped++; continue }
    if (-not (Test-Path -LiteralPath $d)) { continue }
    $short = $d.Substring($Root.Length + 1)
    Write-Host ("[{0,3}/{1}] {2}" -f $n, $Dirs.Count, $(if ($short.Length -gt 78) { $short.Substring(0,78) + '...' } else { $short }))
    if (-not $DryRun) {
        try   { Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction Stop }
        catch { Write-Warning "  failed: $($_.Exception.Message)"; $errors++ }
    }
}
foreach ($f in $Files) {
    if (-not (Test-InScope $f)) { $skipped++; continue }
    if (-not (Test-Path -LiteralPath $f)) { continue }
    Write-Host ("[file] {0}" -f $f.Substring($Root.Length + 1))
    if (-not $DryRun) {
        try   { Remove-Item -LiteralPath $f -Force -ErrorAction Stop }
        catch { Write-Warning "  failed: $($_.Exception.Message)"; $errors++ }
    }
}

$after = (Get-PSDrive C).Free
Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host ("Free space after  : {0:N2} GB" -f ($after/1GB))
Write-Host ("SPACE RECLAIMED   : {0:N2} GB" -f (($after - $before)/1GB)) -ForegroundColor Green
Write-Host ("Refused (guard)   : {0}" -f $skipped)
Write-Host ("Errors            : {0}" -f $errors)
Write-Host ""
Write-Host "To restore a project's dependencies later: cd into it and run 'npm install'"
Write-Host "(or 'pip install -r requirements.txt' for the Python ones)."

