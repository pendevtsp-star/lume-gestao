#!/bin/sh
set -eu

# Backup de producao do Lume Gestao.
# Nao inclui segredos. Mantenha uma copia fora da VPS usando rclone ou storage equivalente.

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
BACKUP_UPLOAD_ENABLED="${BACKUP_UPLOAD_ENABLED:-False}"
BACKUP_RCLONE_REMOTE="${BACKUP_RCLONE_REMOTE:-}"
BACKUP_RCLONE_FLAGS="${BACKUP_RCLONE_FLAGS:-}"
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

case "$(printf '%s' "${BACKUP_UPLOAD_ENABLED}" | tr '[:upper:]' '[:lower:]')" in
  true|1|yes|sim)
    if [ -z "${BACKUP_RCLONE_REMOTE}" ]; then
      echo "[backup] BACKUP_UPLOAD_ENABLED esta ativo, mas BACKUP_RCLONE_REMOTE nao foi configurado."
      exit 2
    fi
    if ! command -v rclone >/dev/null 2>&1; then
      echo "[backup] rclone nao encontrado. Instale e configure um remote antes de ativar upload externo."
      exit 2
    fi
    echo "[backup] Enviando backup para storage externo: ${BACKUP_RCLONE_REMOTE}"
    # shellcheck disable=SC2086
    rclone copy ${BACKUP_RCLONE_FLAGS} "${DB_BACKUP}" "${BACKUP_RCLONE_REMOTE}"
    # shellcheck disable=SC2086
    rclone copy ${BACKUP_RCLONE_FLAGS} "${MEDIA_BACKUP}" "${BACKUP_RCLONE_REMOTE}"
    echo "[backup] Upload externo concluido."
    ;;
  *)
    echo "[backup] Upload externo desativado. Configure BACKUP_UPLOAD_ENABLED=True e BACKUP_RCLONE_REMOTE para ativar."
    ;;
esac
