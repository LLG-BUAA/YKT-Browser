$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean YKTBrowser.spec

$releaseDir = Join-Path $root "release\YKTBrowser"
if (Test-Path $releaseDir) {
    Remove-Item -Recurse -Force $releaseDir
}
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Copy-Item -Recurse -Force (Join-Path $root "dist\YKTBrowser\*") $releaseDir
Copy-Item -Force README.md $releaseDir
Copy-Item -Force requirements.txt $releaseDir

Write-Host "Build completed:"
Write-Host $releaseDir
