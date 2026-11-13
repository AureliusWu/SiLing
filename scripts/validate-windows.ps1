param([string]$Wav)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = '.venv/Scripts/python.exe'
& $python -m siling_voice doctor
if ($LASTEXITCODE -ne 0) { throw 'Doctor failed' }
& $python -m siling_voice models verify
if ($LASTEXITCODE -ne 0) { throw 'Models missing or checksum failed' }
& $python -m siling_voice devices
if ($LASTEXITCODE -ne 0) { throw 'No audio system available' }
if ($Wav) {
  & $python -m siling_voice wav $Wav --output .evidence/windows-wav.json
  if ($LASTEXITCODE -ne 0) { throw 'WAV integration failed' }
}
Write-Host 'Hardware acceptance remains NOT_VERIFIED. Follow docs/windows-acceptance.md.'
& $python -m siling_voice serve
