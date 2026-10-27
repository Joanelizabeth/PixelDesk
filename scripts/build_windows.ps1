# Builds dist\PixelDesk\PixelDesk.exe with PyInstaller.
#   .\scripts\build_windows.ps1            (runs tests first)
#   .\scripts\build_windows.ps1 -SkipTests
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) { & "$PSScriptRoot\setup_dev.ps1" }
$py = ".\.venv\Scripts\python.exe"

if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = "offscreen"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; not building." }
    Remove-Item Env:\QT_QPA_PLATFORM
}

& $py scripts\generate_assets.py
& $py -m PyInstaller --noconfirm --clean pixeldesk.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

Write-Host "`nBuilt: $(Resolve-Path dist\PixelDesk\PixelDesk.exe)"
Write-Host "Copy the whole dist\PixelDesk folder anywhere (e.g. %LOCALAPPDATA%\Programs\PixelDesk)."
Write-Host "User data is stored separately in %LOCALAPPDATA%\PixelDesk."
