# Download the official portable Viewer into W9; does not run an installer or move the robot.
$ErrorActionPreference = 'Stop'
$w9 = Split-Path $PSScriptRoot -Parent
$downloads = Join-Path $w9 'downloads'
New-Item -ItemType Directory -Force -Path $downloads | Out-Null
$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/realsenseai/librealsense/releases/latest'
$asset = @($release.assets | Where-Object { $_.name -match 'RealSense.Viewer.exe$' })
if ($asset.Count -ne 1) { throw 'No unique portable Viewer in the latest stable release. Open the official releases page.' }
$target = Join-Path $downloads $asset[0].name
if (-not (Test-Path -LiteralPath $target)) {
    Invoke-WebRequest -UseBasicParsing -Uri $asset[0].browser_download_url -OutFile $target
}
if ($asset[0].digest -match '^sha256:(.+)$') {
    $expectedDigest = $Matches[1]
    $actualDigest = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actualDigest -ne $expectedDigest) { throw 'Viewer SHA256 differs from GitHub release metadata.' }
}
[pscustomobject]@{
    version = $release.tag_name
    url = $asset[0].browser_download_url
    sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    path = $target
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $downloads 'viewer-install.json')
Write-Host "Viewer ready: $target"
Write-Host 'Close Viewer before Python capture; both cannot use the same camera at once.'
