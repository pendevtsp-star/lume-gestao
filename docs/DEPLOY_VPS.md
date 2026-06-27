# Deploy em VPS Linux

Este roteiro prepara o Lume Gestao para uma VPS Linux barata rodando Docker Compose, PostgreSQL, Nginx, HTTPS e Cloudflare.

## Visao geral

Arquivos principais:

- `docker-compose.prod.yml`: stack de producao com PostgreSQL, migracao, web, worker e Nginx.
- `.env.production.example`: modelo de variaveis sem segredos reais.
- `deploy/nginx/lume.conf`: proxy reverso com HTTPS, static e media.
- `scripts/deploy-migrate.sh`: etapa unica de `check --deploy`, `collectstatic`, migracoes e usuario tecnico.
- `scripts/backup-linux.sh`: backup do banco e da pasta `media`.

## 1. Preparar a VPS

Em Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Saia e entre novamente no SSH para aplicar o grupo `docker`.

## 2. Baixar o projeto

```bash
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd lume-gestao
cp .env.production.example .env.production
```

Edite o arquivo:

```bash
nano .env.production
```

Troque obrigatoriamente:

- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `POSTGRES_PASSWORD`
- variaveis `EMAIL_*`, `GOOGLE_*` e `WHATSAPP_*` quando forem usadas de verdade

Mantenha para dados reais:

```text
DEBUG=False
LUME_STRICT_PRODUCTION=True
LUME_SEED_DEMO=False
WHATSAPP_DRY_RUN=True
```

So coloque `WHATSAPP_DRY_RUN=False` depois de validar templates e conta Meta.

## 3. HTTPS e Cloudflare

Configure o DNS no Cloudflare apontando para o IP da VPS.

Modo recomendado:

- SSL/TLS no Cloudflare: `Full (strict)`.
- Sempre usar HTTPS: ativo.
- Proxy laranja: ativo depois que o servidor responder corretamente.

Coloque os certificados no servidor:

```text
deploy/nginx/certs/fullchain.pem
deploy/nginx/certs/privkey.pem
```

Pode ser certificado de origem do Cloudflare ou certificado emitido por Let's Encrypt. Nao versione esses arquivos.

## 4. Subir producao

Validar a configuracao renderizada:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config
```

Subir:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d
```

Ver status:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f web
```

O servico `migrate` roda uma vez antes do `web` e do `worker`. Assim evitamos duas instancias tentando migrar o banco ao mesmo tempo.

## 5. Atualizar versao

Antes de atualizar:

```bash
sh scripts/backup-linux.sh
```

Depois:

```bash
git pull
docker compose --env-file .env.production -f docker-compose.prod.yml up --build -d
```

## 6. Backup

Backup manual:

```bash
sh scripts/backup-linux.sh
```

Os arquivos ficam em:

```text
backups/
```

Copie os backups para fora da VPS. Exemplo:

```bash
scp backups/lume_db_YYYYMMDD_HHMMSS.sql usuario@outro-servidor:/caminho/seguro/
scp backups/lume_media_YYYYMMDD_HHMMSS.tar.gz usuario@outro-servidor:/caminho/seguro/
```

Para agendar backup diario as 03:00:

```bash
crontab -e
```

Adicionar:

```text
0 3 * * * cd /caminho/lume-gestao && sh scripts/backup-linux.sh >> backups/backup.log 2>&1
```

## 7. Restauracao

Em ambiente separado, com containers ligados:

```bash
cat backups/lume_db_YYYYMMDD_HHMMSS.sql | docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Restaurar media:

```bash
cat backups/lume_media_YYYYMMDD_HHMMSS.tar.gz | docker compose --env-file .env.production -f docker-compose.prod.yml exec -T web tar -xzf - -C /app
```

Teste restauracao antes de considerar o backup confiavel.

## 8. API mobile

A API web continua protegida por sessao. Para o futuro app mobile, existe endpoint inicial de token:

```text
POST /api/v1/mobile/auth/token/
```

Payload:

```json
{
  "username": "usuario",
  "password": "senha"
}
```

Resposta:

```json
{
  "token": "..."
}
```

Chamadas mobile devem enviar:

```text
Authorization: Token ...
```

Antes de liberar app mobile publico, revisar expiracao/rotacao de tokens, rate limit, logout remoto e testes de permissao por objeto.

## 9. Checklist antes de dados reais

- `docker compose --env-file .env.production -f docker-compose.prod.yml config` sem erros.
- `LUME_STRICT_PRODUCTION=True`.
- `LUME_SEED_DEMO=False`.
- HTTPS respondendo com certificado valido.
- Cloudflare em `Full (strict)`.
- Backup criado e restaurado em ambiente separado.
- Senhas padrao removidas.
- SMTP testado.
- WhatsApp em dry-run ate validacao final.
- Logs do `web`, `worker` e `nginx` sem erro recorrente.
