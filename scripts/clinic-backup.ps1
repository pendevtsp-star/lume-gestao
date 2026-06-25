$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = "backups"
$dbBackup = Join-Path $backupDir "lume_db_$timestamp.sql"
$mediaBackup = Join-Path $backupDir "lume_media_$timestamp.zip"

if (-not (Test-Path $backupDir)) {
  New-Item -ItemType Directory -Path $backupDir | Out-Null
}

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | Out-File -Encoding utf8 $dbBackup

if (Test-Path "media") {
  Compress-Archive -Path "media" -DestinationPath $mediaBackup -Force
}

Write-Host "Backup do banco criado em: $dbBackup"
if (Test-Path $mediaBackup) {
  Write-Host "Backup das fotos/anexos criado em: $mediaBackup"
}
