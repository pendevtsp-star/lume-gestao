#!/bin/sh
set -eu

python manage.py collectstatic --noinput
python manage.py migrate
python manage.py ensure_maintenance_user

if [ "${LUME_SEED_DEMO:-False}" = "True" ]; then
  python manage.py seed_demo
fi

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${LUME_GUNICORN_WORKERS:-3}" \
  --timeout "${LUME_GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
