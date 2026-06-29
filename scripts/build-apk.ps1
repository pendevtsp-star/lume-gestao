param(
  [string]$ApiBaseUrl = "https://sistema.clinicafisiolume.com.br",
  [switch]$AllowInsecureHttp
)

$ErrorActionPreference = "Stop"

$ProductionApiBaseUrl = "https://sistema.clinicafisiolume.com.br"
$parsedApiBaseUrl = [Uri]$ApiBaseUrl
$localHosts = @("localhost", "127.0.0.1", "10.0.2.2")
$blockedHosts = @("clinicalumefisio.com.br", "clinicafisiolume.com.br", "www.clinicafisiolume.com.br")
$normalizedApiBaseUrl = $ApiBaseUrl.TrimEnd("/")

if (-not $AllowInsecureHttp -and $normalizedApiBaseUrl -ne $ProductionApiBaseUrl) {
  throw "Build de producao bloqueado: use exatamente $ProductionApiBaseUrl."
}

if (-not $AllowInsecureHttp -and ($parsedApiBaseUrl.Scheme -ne "https" -or $localHosts -contains $parsedApiBaseUrl.Host -or $blockedHosts -contains $parsedApiBaseUrl.Host)) {
  throw "Build de producao bloqueado: URL local ou dominio incorreto detectado em LUME_API_BASE_URL."
}

$Root = Split-Path -Parent $PSScriptRoot
$AppDir = Join-Path $Root "apps\lume_app"

Push-Location $AppDir
flutter pub get
flutter build apk --release `
  --dart-define=LUME_API_BASE_URL=$ApiBaseUrl `
  --dart-define=LUME_ALLOW_INSECURE_HTTP=$($AllowInsecureHttp.IsPresent.ToString().ToLower())
Pop-Location

Write-Host "APK gerado em apps\lume_app\build\app\outputs\flutter-apk\app-release.apk"
