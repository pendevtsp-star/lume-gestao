# Desenvolvimento local

Este guia descreve os comandos reproduziveis usados pelo projeto. Ele nao deve
ser executado contra a base de producao.

## Pre-requisitos

- Python 3.12
- Docker Desktop com Docker Compose v2
- Node.js 20 para trabalhar diretamente no gateway WhatsApp
- Flutter stable apenas quando `apps/lume_app/` for retomado

Crie o arquivo local a partir do exemplo e mantenha os valores reais fora do
Git:

```powershell
Copy-Item .env.example .env
```

## Execucao com Python no Windows

```powershell
.\scripts\dev.ps1
```

Encerramento:

```powershell
.\scripts\stop-dev.ps1
```

## Execucao com Docker

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 web worker whatsapp-web
```

Parada sem apagar volumes:

```bash
docker compose down
```

Nao use `docker compose down -v` quando houver dados a preservar.

## Checks Django

Com o ambiente virtual local:

```powershell
$env:DB_ENGINE='sqlite'
$env:LUME_STRICT_PRODUCTION='False'
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
$env:DJANGO_SETTINGS_MODULE='config.test_settings'
.\.venv\Scripts\python.exe manage.py test
```

Com Docker:

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test
```

Os overrides SQLite acima valem somente para o processo local. Eles nao devem
ser gravados no `.env` de producao.

## Checks de infraestrutura

```bash
docker compose -f docker-compose.yml config --quiet
LUME_APP_IMAGE=ghcr.io/pendevtsp-star/lume-gestao/app:ci \
LUME_WHATSAPP_WEB_IMAGE=ghcr.io/pendevtsp-star/lume-gestao/whatsapp-web:ci \
docker compose -f docker-compose.prod.yml config --quiet
```

Gateway WhatsApp:

```bash
cd whatsapp-web-gateway
npm ci --omit=dev --omit=optional
node --check src/server.js
npm test
npm audit --omit=dev --omit=optional --audit-level=high
```

## App Flutter pausado

O app nao participa dos checks web. Quando qualquer arquivo em
`apps/lume_app/**` muda, o workflow dedicado executa:

```bash
cd apps/lume_app
flutter pub get
flutter analyze
flutter test
```

## Antes de solicitar publicacao

1. Execute checks e testes afetados pela mudanca.
2. Execute `git diff --check`.
3. Confirme que migrations esperadas foram criadas e revisadas.
4. Confirme que `.env`, dados, midia e backups nao aparecem no diff.
5. Registre qualquer integracao externa que nao pode ser validada localmente.
