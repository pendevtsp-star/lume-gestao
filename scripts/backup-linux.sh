#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DB_BACKUP="${BACKUP_DIR}/lume_db_${TIMESTAMP}.sql"
MEDIA_BACKUP="${BACKUP_DIR}/lume_media_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "${DB_BACKUP}"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T web sh -c 'tar -czf - -C /app media 2>/dev/null || true' > "${MEDIA_BACKUP}"

echo "Backup do banco criado em: ${DB_BACKUP}"
echo "Backup de media criado em: ${MEDIA_BACKUP}"
