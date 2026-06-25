$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$DesktopDir = Join-Path $Root "desktop"
$BackendBin = Join-Path $DesktopDir "backend-bin"

if (-not (Test-Path (Join-Path $Root ".venv"))) {
  python -m venv (Join-Path $Root ".venv")
}

& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install -r (Join-Path $Root "requirements.txt")
& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install pyinstaller

if (Test-Path $BackendBin) {
  Remove-Item -Recurse -Force $BackendBin
}

& (Join-Path $Root ".venv\Scripts\python.exe") -m PyInstaller `
  --name lume-backend `
  --onedir `
  --distpath $BackendBin `
  --workpath (Join-Path $Root "dist\pyinstaller-work") `
  --specpath (Join-Path $Root "dist\pyinstaller-spec") `
  --add-data "$($Root)\templates;templates" `
  --add-data "$($Root)\static;static" `
  --collect-all django `
  --collect-all rest_framework `
  --collect-all django_filters `
  --collect-submodules config `
  --collect-submodules accounts `
  --collect-submodules billing `
  --collect-submodules core `
  --collect-submodules patients `
  --collect-submodules reports `
  --collect-submodules scheduling `
  --collect-submodules team `
  (Join-Path $Root "desktop\backend_entry.py")

Push-Location $DesktopDir
npm install
npm run dist:win
Pop-Location
