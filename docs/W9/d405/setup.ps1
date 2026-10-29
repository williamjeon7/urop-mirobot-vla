# Run on the Windows laptop connected to D405/Mirobot, in local PowerShell.
$ErrorActionPreference = 'Stop'
$w9 = Split-Path $PSScriptRoot -Parent
$repo = Split-Path (Split-Path $w9 -Parent) -Parent
Set-Location $repo
$python = Join-Path $w9 '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    py -3.10 -m venv (Join-Path $w9 '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 venv creation failed.' }
}
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
& $python -m pip freeze | Set-Content -Encoding utf8 (Join-Path $w9 'installed-packages.local.txt')
& $python -m docs.W9.d405.capture --list
if ($LASTEXITCODE -ne 0) { throw 'D405 device query failed.' }
Write-Host 'Installed. Read docs/W9/D405_GUIDE.md. No robot commands were sent.'
