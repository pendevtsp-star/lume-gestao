param(
  [Parameter(Mandatory = $true)]
  [string]$SshTarget,

  [string]$RemoteDir = "/srv/lume-gestao",
  [string]$ArchivePath = "dist\lume-gestao-vps.tar.gz",
  [string]$SshKey = "",
  [switch]$SkipBackup,
  [switch]$SkipNginxReload,
  [switch]$SkipDockerBuildCachePrune,
  [string]$DockerBuildCacheMinAge = "24h",
  [string]$DockerBuildCacheKeepStorage = "8GB"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ArchiveFullPath = Join-Path $Root $ArchivePath
$ArchiveDir = Split-Path -Parent $ArchiveFullPath

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
  throw "ssh nao encontrado no PATH."
}

if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
  throw "scp nao encontrado no PATH."
}

New-Item -ItemType Directory -Force $ArchiveDir | Out-Null

Push-Location $Root
if (Test-Path $ArchiveFullPath) {
  Remove-Item -LiteralPath $ArchiveFullPath -Force
}

tar `
  --exclude='.git' `
  --exclude='.venv' `
  --exclude='.env' `
  --exclude='db.sqlite3' `
  --exclude='media' `
  --exclude='data' `
  --exclude='dist' `
  --exclude='desktop/node_modules' `
  --exclude='desktop/backend-bin' `
  --exclude='apps/lume_app/build' `
  --exclude='*.pyc' `
  --exclude='__pycache__' `
  -czf $ArchiveFullPath .
Pop-Location

$sshArgs = @()
if ($SshKey) {
  $sshArgs += @("-i", $SshKey)
}

$remoteArchive = "/tmp/lume-gestao-vps.tar.gz"

Write-Host "[deploy] Enviando pacote para $SshTarget..."
& scp @sshArgs $ArchiveFullPath "${SshTarget}:$remoteArchive"

$backupCommand = "if [ -f scripts/backup-production.sh ]; then sh scripts/backup-production.sh; else echo '[deploy] backup script ainda nao existe no remoto'; fi"
if ($SkipBackup) {
  $backupCommand = "echo '[deploy] backup ignorado por parametro'"
}

$nginxCommand = "if command -v nginx >/dev/null 2>&1; then sudo nginx -t && sudo systemctl reload nginx; else echo '[deploy] nginx nao instalado no host'; fi"
if ($SkipNginxReload) {
  $nginxCommand = "echo '[deploy] reload nginx ignorado por parametro'"
}

$dockerBuildCachePruneCommand = @"
echo '[deploy] Limpando cache antigo de build Docker'
docker builder prune -f --filter 'until=$DockerBuildCacheMinAge' --keep-storage '$DockerBuildCacheKeepStorage' || echo '[deploy] aviso: limpeza de cache Docker falhou; deploy mantido'
docker system df
"@
if ($SkipDockerBuildCachePrune) {
  $dockerBuildCachePruneCommand = "echo '[deploy] limpeza de cache Docker ignorada por parametro'"
}

$remoteScript = @"
set -eu
echo '[deploy] Preparando diretorio $RemoteDir'
sudo mkdir -p '$RemoteDir'
sudo chown "`$USER:`$USER" '$RemoteDir'
cd '$RemoteDir'

if [ ! -f .env ]; then
  echo '[deploy] ERRO: .env real nao encontrado em $RemoteDir/.env'
  echo '[deploy] Crie o .env na VPS a partir de .env.production.example antes do deploy.'
  exit 2
fi

echo '[deploy] Backup antes da atualizacao'
$backupCommand

echo '[deploy] Extraindo pacote'
tar -xzf '$remoteArchive' -C '$RemoteDir'
rm -f '$remoteArchive'

echo '[deploy] Validando compose'
docker compose -f docker-compose.prod.yml config >/dev/null

echo '[deploy] Recriando containers sem remover volumes'
docker compose -f docker-compose.prod.yml up -d --build

echo '[deploy] Status dos containers'
docker compose -f docker-compose.prod.yml ps

echo '[deploy] Validando healthcheck local'
sleep 5
health_host="`$(grep -E '^LUME_HEALTHCHECK_HOST=' .env | tail -n1 | cut -d= -f2-)"
if [ -z "`$health_host" ]; then
  health_host='sistema.clinicafisiolume.com.br'
fi
curl -fsS -H "Host: `$health_host" -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/healthz/

$dockerBuildCachePruneCommand

echo '[deploy] Recarregando Nginx, se existir'
$nginxCommand

echo '[deploy] Deploy concluido'
"@
$remoteScript = $remoteScript -replace "`r`n", "`n"

Write-Host "[deploy] Executando comandos remotos..."
& ssh @sshArgs $SshTarget $remoteScript

Write-Host "[deploy] Pacote local: $ArchiveFullPath"
