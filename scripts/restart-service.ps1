#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$LogDir = 'C:\code\git-viewer\logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
Start-Transcript -Path (Join-Path $LogDir 'restart.log') -Force | Out-Null
trap { Write-Host "ERROR: $_"; Stop-Transcript | Out-Null; exit 1 }

# Truncate old service logs for a clean view.
foreach ($f in @('service.stdout.log','service.stderr.log')) {
    $p = Join-Path $LogDir $f
    if (Test-Path $p) { Clear-Content $p }
}

$nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $nssm) {
    $nssm = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\nssm.exe"
}
Write-Host "nssm: $nssm"

# Stop/reset/start to clear the Paused state.
$svc = Get-Service -Name 'git-viewer' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -ne 'Stopped') {
    & $nssm stop git-viewer
}
Start-Sleep -Seconds 1
& $nssm start git-viewer

Start-Sleep -Seconds 2
Get-Service -Name 'git-viewer' | Format-List Name, Status, StartType
Stop-Transcript | Out-Null
