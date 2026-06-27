#!/bin/sh
set -eu

if [ "${LUME_RUN_MIGRATIONS_ON_START:-True}" = "True" ]; then
  python manage.py migrate --noinput
  python manage.py ensure_maintenance_user

  if [ "${LUME_SEED_DEMO:-False}" = "True" ]; then
    python manage.py seed_demo
  fi
fi

while true; do
  python manage.py process_whatsapp_queue --limit "${LUME_QUEUE_BATCH_SIZE:-50}"
  sleep "${LUME_JOB_INTERVAL_SECONDS:-60}"
done
