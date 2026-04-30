#Requires -RunAsAdministrator
# Installs git-viewer as a Windows service via NSSM.
# Run from an elevated PowerShell.

$ErrorActionPreference = 'Stop'

$ServiceName = 'git-viewer'
$RepoDir     = 'C:\code\git-viewer'
$PythonExe   = 'C:\Python314\python.exe'
$AppScript   = Join-Path $RepoDir 'app.py'
$LogDir      = Join-Path $RepoDir 'logs'
$InstallLog  = Join-Path $LogDir 'install.log'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
Start-Transcript -Path $InstallLog -Force | Out-Null
trap { Write-Host "ERROR: $_"; Stop-Transcript | Out-Null; exit 1 }

Write-Host "[1/5] Ensuring NSSM is installed..."
$nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
if (-not $nssm) {
    winget install --id NSSM.NSSM -e --silent --accept-source-agreements --accept-package-agreements
    # winget updates PATH for new shells only; probe common install locations.
    $candidates = @(
        "$env:ProgramFiles\NSSM\nssm.exe",
        "$env:ProgramFiles(x86)\NSSM\nssm.exe"
    )
    $wingetLinks = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Links" -Filter 'nssm.exe' -ErrorAction SilentlyContinue
    if ($wingetLinks) { $candidates += $wingetLinks.FullName }
    $wingetPkgs = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter 'nssm.exe' -ErrorAction SilentlyContinue
    if ($wingetPkgs) { $candidates += $wingetPkgs.FullName }
    $nssm = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $nssm) { throw "NSSM install succeeded but nssm.exe not found." }
}
Write-Host "      nssm: $nssm"

Write-Host "[2/5] Removing existing service if present..."
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Status -ne 'Stopped') { & $nssm stop $ServiceName | Out-Null }
    & $nssm remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 1
}

Write-Host "[3/5] Installing service..."
& $nssm install $ServiceName $PythonExe $AppScript
& $nssm set $ServiceName AppDirectory $RepoDir
& $nssm set $ServiceName DisplayName 'Git Viewer'
& $nssm set $ServiceName Description 'Read-only web UI for browsing local git repositories (port 5125)'
& $nssm set $ServiceName Start SERVICE_AUTO_START
& $nssm set $ServiceName AppStdout (Join-Path $LogDir 'service.stdout.log')
& $nssm set $ServiceName AppStderr (Join-Path $LogDir 'service.stderr.log')
& $nssm set $ServiceName AppRotateFiles 1
& $nssm set $ServiceName AppRotateOnline 1
& $nssm set $ServiceName AppRotateBytes 10485760
& $nssm set $ServiceName AppEnvironmentExtra 'PYTHONIOENCODING=utf-8' 'PYTHONUNBUFFERED=1'

Write-Host "[4/5] Starting service..."
& $nssm start $ServiceName

Write-Host "[5/5] Status:"
Start-Sleep -Seconds 2
Get-Service -Name $ServiceName | Format-List Name, Status, StartType, DisplayName

Write-Host "Done."
Stop-Transcript | Out-Null
