#!/bin/sh
set -eu

# Restauracao de producao do Lume Gestao.
# Teste este fluxo em ambiente separado antes de colocar dados reais em producao.
#
# Uso:
#   sh scripts/restore-production.sh backups/lume_db_YYYYMMDD_HHMMSS.sql backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
#
# Variaveis opcionais:
#   COMPOSE_FILE=docker-compose.prod.yml
#   ENV_FILE=.env

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env}"
DB_DUMP="${1:-}"
MEDIA_ARCHIVE="${2:-}"

if [ -z "${DB_DUMP}" ]; then
  echo "Uso: sh scripts/restore-production.sh CAMINHO_DUMP_SQL [CAMINHO_MEDIA_TAR_GZ]"
  exit 2
fi

if [ ! -f "${DB_DUMP}" ]; then
  echo "[restore] Dump SQL nao encontrado: ${DB_DUMP}"
  exit 2
fi

if [ -n "${MEDIA_ARCHIVE}" ] && [ ! -f "${MEDIA_ARCHIVE}" ]; then
  echo "[restore] Arquivo de media nao encontrado: ${MEDIA_ARCHIVE}"
  exit 2
fi

echo "[restore] ATENCAO: esta operacao pode sobrescrever dados atuais."
echo "[restore] Dump SQL: ${DB_DUMP}"
if [ -n "${MEDIA_ARCHIVE}" ]; then
  echo "[restore] Media: ${MEDIA_ARCHIVE}"
else
  echo "[restore] Media: nao sera restaurada."
fi
printf "[restore] Digite RESTAURAR para continuar: "
read confirmation

if [ "${confirmation}" != "RESTAURAR" ]; then
  echo "[restore] Restauracao cancelada."
  exit 1
fi

echo "[restore] Restaurando banco PostgreSQL..."
cat "${DB_DUMP}" | docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

if [ -n "${MEDIA_ARCHIVE}" ]; then
  echo "[restore] Restaurando media..."
  cat "${MEDIA_ARCHIVE}" | docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T web tar -xzf - -C /app
fi

echo "[restore] Restauracao concluida. Reinicie os servicos se necessario:"
echo "[restore] docker compose -f ${COMPOSE_FILE} restart web worker"
