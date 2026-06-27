#!/bin/sh
set -eu

python manage.py check --deploy
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py ensure_maintenance_user

if [ "${LUME_SEED_DEMO:-False}" = "True" ]; then
  python manage.py seed_demo
fi
