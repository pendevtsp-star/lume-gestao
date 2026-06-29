#!/bin/sh
set -eu

echo "[worker] Iniciando worker de tarefas recorrentes..."

if [ "${LUME_WORKER_RUN_MIGRATIONS:-False}" = "True" ]; then
  echo "[worker] Aplicando migracoes por configuracao explicita..."
  python manage.py migrate --noinput

  echo "[worker] Garantindo usuario tecnico, se habilitado..."
  python manage.py ensure_maintenance_user
else
  echo "[worker] Migracoes desativadas no worker. O web/deploy deve cuidar do bootstrap."
fi

if [ "${LUME_SEED_DEMO:-False}" = "True" ]; then
  if [ "${ENVIRONMENT:-development}" = "production" ]; then
    echo "[worker] Seed demo ignorado no worker em producao."
  else
    echo "[worker] Criando/atualizando dados demonstrativos em ambiente nao-producao..."
    python manage.py seed_demo
  fi
fi

while true; do
  echo "[worker] Processando fila WhatsApp..."
  python manage.py process_whatsapp_queue --limit "${LUME_QUEUE_BATCH_SIZE:-50}"

  case "$(printf '%s' "${HOMECARE_UPLOAD_WORKER_ENABLED:-False}" | tr '[:upper:]' '[:lower:]')" in
    true|1|yes|sim)
      echo "[worker] Processando uploads do Lume em casa..."
      python manage.py process_homecare_uploads --limit "${HOMECARE_UPLOAD_BATCH_SIZE:-3}"
      ;;
    *)
      echo "[worker] Uploads do Lume em casa desativados neste ambiente."
      ;;
  esac

  echo "[worker] Ciclo concluido. Aguardando ${LUME_JOB_INTERVAL_SECONDS:-60}s..."
  sleep "${LUME_JOB_INTERVAL_SECONDS:-60}"
done
