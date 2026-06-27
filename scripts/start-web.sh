#!/bin/sh
set -eu

echo "[web] Iniciando Lume Gestao web..."

if [ "${LUME_RUN_MIGRATIONS_ON_START:-True}" = "True" ]; then
  echo "[web] Coletando arquivos estaticos..."
  python manage.py collectstatic --noinput

  echo "[web] Aplicando migracoes do banco..."
  python manage.py migrate --noinput

  echo "[web] Garantindo usuario tecnico, se habilitado..."
  python manage.py ensure_maintenance_user

  if [ "${LUME_SEED_DEMO:-False}" = "True" ]; then
    echo "[web] Criando/atualizando dados demonstrativos..."
    python manage.py seed_demo
  else
    echo "[web] Seed demo desativado."
  fi
else
  echo "[web] Bootstrap inicial desativado por LUME_RUN_MIGRATIONS_ON_START=False."
fi

echo "[web] Iniciando Gunicorn em 0.0.0.0:8000..."
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${LUME_GUNICORN_WORKERS:-3}" \
  --timeout "${LUME_GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
