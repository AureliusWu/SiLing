param([switch]$Demo)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (!(Test-Path '.venv/Scripts/python.exe')) { py -3.12 -m venv .venv }
& .venv/Scripts/python.exe -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed' }
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
if ($Demo) { & .venv/Scripts/python.exe scripts/run_dev.py --demo }
else { & .venv/Scripts/python.exe scripts/run_dev.py }
