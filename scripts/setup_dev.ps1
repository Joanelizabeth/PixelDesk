# Creates an isolated virtual environment in .venv and installs dependencies.
# Usage (PowerShell, from the project folder):  .\scripts\setup_dev.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Find-Python {
    foreach ($candidate in @(@("py", "-3.12"), @("py", "-3"), @("python"))) {
        try {
            $exe = $candidate[0]; $args = $candidate[1..($candidate.Length - 1)]
            & $exe @args -c "import sys; assert sys.version_info >= (3, 10)" 2>$null
            if ($LASTEXITCODE -eq 0) { return ,$candidate }
        } catch { }
    }
    throw "Python 3.10+ was not found. Install Python 3.12 from https://www.python.org/downloads/ and re-run."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $py = Find-Python
    $exe = $py[0]; $pyArgs = $py[1..($py.Length - 1)]
    Write-Host "Creating virtual environment with: $($py -join ' ')"
    & $exe @pyArgs -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Write-Host "`nReady. Run Pixel Desk with:  .\scripts\run_dev.ps1"
