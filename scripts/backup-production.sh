#!/bin/sh
set -eu

# Backup de producao do Lume Gestao.
# Nao inclui segredos. Copie os arquivos gerados para storage externo seguro.
# Sugestoes: rclone, S3/Backblaze B2, snapshot criptografado ou outro storage fora da VPS.

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

DB_BACKUP="${BACKUP_DIR}/lume_db_${TIMESTAMP}.sql"
MEDIA_BACKUP="${BACKUP_DIR}/lume_media_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "[backup] Iniciando backup em ${TIMESTAMP}..."
echo "[backup] Gerando dump PostgreSQL..."
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "${DB_BACKUP}"

echo "[backup] Compactando media..."
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T web sh -c 'tar -czf - -C /app media 2>/dev/null || true' > "${MEDIA_BACKUP}"

echo "[backup] Removendo backups com mais de ${RETENTION_DAYS} dia(s)..."
find "${BACKUP_DIR}" -type f \( -name 'lume_db_*.sql' -o -name 'lume_media_*.tar.gz' \) -mtime +"${RETENTION_DAYS}" -delete

echo "[backup] Banco: ${DB_BACKUP}"
echo "[backup] Media: ${MEDIA_BACKUP}"
echo "[backup] Envie uma copia para fora da VPS. Exemplo:"
echo "[backup] rclone copy ${BACKUP_DIR}/ remote:lume-gestao/backups/"
