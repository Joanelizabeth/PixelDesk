# Runs Pixel Desk from source. Pass -Window to force normal window mode, -Verbose for debug logs.
#   .\scripts\run_dev.ps1
#   .\scripts\run_dev.ps1 -Window
param([switch]$Window, [switch]$DebugLog)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) { & "$PSScriptRoot\setup_dev.ps1" }
$argsList = @("main.py")
if ($Window) { $argsList += "--window" }
if ($DebugLog) { $argsList += "--verbose" }
& .\.venv\Scripts\python.exe @argsList
