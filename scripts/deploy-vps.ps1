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
  [string]$DockerBuildCacheKeepStorage = "8GB",
  [string]$ReleaseCommit = "",
  [string]$ReleaseBranch = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ArchiveFullPath = Join-Path $Root $ArchivePath
$ArchiveDir = Split-Path -Parent $ArchiveFullPath

if (-not $ReleaseCommit) {
  $ReleaseCommit = (git -C $Root rev-parse HEAD).Trim()
}

if (-not $ReleaseBranch) {
  $ReleaseBranch = (git -C $Root branch --show-current).Trim()
}

$ReleaseRecordedAt = Get-Date -Format "yyyyMMdd_HHmmss"

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
  --exclude='.agents' `
  --exclude='.codex' `
  --exclude='.impeccable' `
  --exclude='.github/hooks' `
  --exclude='.github/skills' `
  --exclude='.venv' `
  --exclude='.env' `
  --exclude='db.sqlite3' `
  --exclude='media' `
  --exclude='data' `
  --exclude='backups' `
  --exclude='tmp' `
  --exclude='dist' `
  --exclude='.codex-tmp' `
  --exclude='.codex-remote-attachments' `
  --exclude='desktop/node_modules' `
  --exclude='desktop/backend-bin' `
  --exclude='apps/lume_app/.dart_tool' `
  --exclude='apps/lume_app/build' `
  --exclude='apps/lume_app/android/.gradle' `
  --exclude='apps/lume_app/.idea' `
  --exclude='*.tar.gz' `
  --exclude='*.pyc' `
  --exclude='__pycache__' `
  -czf $ArchiveFullPath .
Pop-Location

$RemoteCleanupScript = "/srv/recovery/safe-vps-cleanup.sh"
$LocalCleanupScript = Join-Path $Root "scripts\safe-vps-cleanup.sh"

$sshArgs = @()
if ($SshKey) {
  $sshArgs += @("-i", $SshKey)
}

$remoteArchive = "/tmp/lume-gestao-vps.tar.gz"

Write-Host "[deploy] Enviando pacote para $SshTarget..."
# The VPS accepts legacy SCP reliably; Windows' SFTP-backed scp can report a
# false remote stat error after completing the upload.
& scp -O @sshArgs $ArchiveFullPath "${SshTarget}:$remoteArchive"
if ($LASTEXITCODE -ne 0) {
  throw "Falha ao enviar o pacote para a VPS (scp exit code $LASTEXITCODE)."
}

$backupCommand = "if [ -f scripts/backup-production.sh ]; then sh scripts/backup-production.sh; else echo '[deploy] backup script ainda nao existe no remoto'; fi"
if ($SkipBackup) {
  $backupCommand = "echo '[deploy] backup ignorado por parametro'"
}

$nginxCommand = "if command -v nginx >/dev/null 2>&1; then sudo nginx -t && sudo systemctl reload nginx; else echo '[deploy] nginx nao instalado no host'; fi"
if ($SkipNginxReload) {
  $nginxCommand = "echo '[deploy] reload nginx ignorado por parametro'"
}

$dockerBuildCachePruneCommand = @"
echo '[deploy] Executando limpeza segura pos-deploy'
  RECOVERY_DIR='/srv/recovery' \
  PROJECT_DIR='$RemoteDir' \
  COMPOSE_FILE='docker-compose.prod.yml' \
  HEALTH_URL='https://sistema.clinicafisiolume.com.br/healthz/' \
  POST_DEPLOY_MIN_AGE='$DockerBuildCacheMinAge' \
  POST_DEPLOY_RESERVED_SPACE='$DockerBuildCacheKeepStorage' \
  '$RemoteCleanupScript' --mode post-deploy || echo '[deploy] aviso: limpeza de cache Docker falhou; deploy mantido'
"@
if ($SkipDockerBuildCachePrune) {
  $dockerBuildCachePruneCommand = "echo '[deploy] limpeza de cache Docker ignorada por parametro'"
}

Write-Host "[deploy] Instalando script de limpeza segura em $RemoteCleanupScript..."
& scp -O @sshArgs $LocalCleanupScript "${SshTarget}:$remoteArchive.cleanup"
if ($LASTEXITCODE -ne 0) {
  throw "Falha ao enviar o script de limpeza para a VPS (scp exit code $LASTEXITCODE)."
}

$remoteScript = @"
set -eu
sudo mkdir -p '/srv/recovery/logs'
sudo install -m 755 '$remoteArchive.cleanup' '$RemoteCleanupScript'
rm -f '$remoteArchive.cleanup'

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

echo '[deploy] Validando healthcheck publico'
sleep 5
health_host="`$(grep -E '^LUME_HEALTHCHECK_HOST=' .env | tail -n1 | cut -d= -f2-)"
if [ -z "`$health_host" ] || [ "`$health_host" = '0.0.0.0' ] || [ "`$health_host" = '127.0.0.1' ] || [ "`$health_host" = 'localhost' ]; then
  health_host='sistema.clinicafisiolume.com.br'
fi
health_url="https://`$health_host/healthz/"
echo "[deploy] Healthcheck: `$health_url"
curl --retry 6 --retry-delay 2 --retry-all-errors -fsS "`$health_url"

echo '[deploy] Registrando versao efetivamente publicada'
cat > PRODUCTION_VERSION <<'EOF'
project=lume-gestao
tag=production-$ReleaseRecordedAt
commit=$ReleaseCommit
branch=$ReleaseBranch
recorded_at=$ReleaseRecordedAt
source=github.com/pendevtsp-star/lume-gestao
EOF

$dockerBuildCachePruneCommand

echo '[deploy] Recarregando Nginx, se existir'
$nginxCommand

echo '[deploy] Deploy concluido'
"@
$remoteScript = $remoteScript -replace "`r`n", "`n"

Write-Host "[deploy] Executando comandos remotos..."
& ssh @sshArgs $SshTarget $remoteScript
if ($LASTEXITCODE -ne 0) {
  throw "Deploy remoto falhou (ssh exit code $LASTEXITCODE)."
}

Write-Host "[deploy] Pacote local: $ArchiveFullPath"
