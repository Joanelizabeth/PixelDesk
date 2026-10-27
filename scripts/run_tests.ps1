# Runs the automated test suite (Windows APIs are mocked; Qt runs offscreen).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) { & "$PSScriptRoot\setup_dev.ps1" }
$env:QT_QPA_PLATFORM = "offscreen"
& .\.venv\Scripts\python.exe -m pytest -v
