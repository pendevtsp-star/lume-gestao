#!/bin/sh
set -eu

python manage.py migrate
python manage.py ensure_maintenance_user

if [ "${LUME_SEED_DEMO:-False}" = "True" ]; then
  python manage.py seed_demo
fi

while true; do
  python manage.py process_whatsapp_queue --limit "${LUME_QUEUE_BATCH_SIZE:-50}"
  sleep "${LUME_JOB_INTERVAL_SECONDS:-60}"
done
