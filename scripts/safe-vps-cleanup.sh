#!/usr/bin/env bash
set -euo pipefail

MODE_VALUE="weekly"
if [[ "${1:-}" == "--mode" ]]; then
  MODE_VALUE="${2:-weekly}"
fi

RECOVERY_DIR="${RECOVERY_DIR:-/srv/recovery}"
LOG_DIR="${LOG_DIR:-$RECOVERY_DIR/logs}"
PROJECT_DIR="${PROJECT_DIR:-/srv/lume-gestao}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
HEALTH_URL="${HEALTH_URL:-https://sistema.clinicafisiolume.com.br/healthz/}"
WEEKLY_MIN_AGE="${WEEKLY_MIN_AGE:-24h}"
POST_DEPLOY_MIN_AGE="${POST_DEPLOY_MIN_AGE:-12h}"
WEEKLY_RESERVED_SPACE="${WEEKLY_RESERVED_SPACE:-8GB}"
POST_DEPLOY_RESERVED_SPACE="${POST_DEPLOY_RESERVED_SPACE:-8GB}"

mkdir -p "$LOG_DIR"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="$LOG_DIR/safe-vps-cleanup_${MODE_VALUE}_${TIMESTAMP}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[cleanup] modo: $MODE_VALUE"
echo "[cleanup] iniciado em: $(date -Is)"

case "$MODE_VALUE" in
  weekly)
    MIN_AGE="$WEEKLY_MIN_AGE"
    RESERVED_SPACE="$WEEKLY_RESERVED_SPACE"
    ;;
  post-deploy)
    MIN_AGE="$POST_DEPLOY_MIN_AGE"
    RESERVED_SPACE="$POST_DEPLOY_RESERVED_SPACE"
    ;;
  *)
    echo "[cleanup] ERRO: modo invalido: $MODE_VALUE"
    exit 2
    ;;
esac

echo "[cleanup] uso antes"
df -h /
echo "[cleanup] docker buildx antes"
docker buildx du | tail -n 5 || true

echo "[cleanup] prune do cache de build"
docker builder prune -af --filter "until=$MIN_AGE" --reserved-space "$RESERVED_SPACE"

echo "[cleanup] uso depois"
df -h /
echo "[cleanup] docker buildx depois"
docker buildx du | tail -n 5 || true

if [ -d "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/$COMPOSE_FILE" ]; then
  echo "[cleanup] validando containers do Lume"
  (
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" ps
  )
fi

echo "[cleanup] validando health publico"
curl -fsSL "$HEALTH_URL"

echo "[cleanup] concluido em: $(date -Is)"
