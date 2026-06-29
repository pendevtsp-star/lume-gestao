param(
  [string]$ApiBaseUrl = "https://sistema.clinicafisiolume.com.br",
  [switch]$AllowInsecureHttp
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$AppDir = Join-Path $Root "apps\lume_app"

Push-Location $AppDir
flutter pub get
flutter build apk --release `
  --dart-define=LUME_API_BASE_URL=$ApiBaseUrl `
  --dart-define=LUME_ALLOW_INSECURE_HTTP=$($AllowInsecureHttp.IsPresent.ToString().ToLower())
Pop-Location

Write-Host "APK gerado em apps\lume_app\build\app\outputs\flutter-apk\app-release.apk"
