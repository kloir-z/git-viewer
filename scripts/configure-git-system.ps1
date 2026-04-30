#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$LogDir = 'C:\code\git-viewer\logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
Start-Transcript -Path (Join-Path $LogDir 'configure-git-system.log') -Force | Out-Null
trap { Write-Host "ERROR: $_"; Stop-Transcript | Out-Null; exit 1 }

# Allow git to operate on repos regardless of the owner/executor mismatch.
# Needed because the service runs as LocalSystem but repos are owned by a regular user.
& git config --system --add safe.directory '*'
Write-Host "--- system config safe.directory ---"
& git config --system --get-all safe.directory

Stop-Transcript | Out-Null
