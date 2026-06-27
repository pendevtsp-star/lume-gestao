# Deploy em VPS Linux

Este roteiro prepara o Lume Gestao para uma VPS Linux barata rodando Docker Compose, PostgreSQL, Nginx, HTTPS e Cloudflare.

## Visao geral

Arquivos principais:

- `docker-compose.prod.yml`: stack de producao com PostgreSQL, web/Django/Gunicorn e worker.
- `.env.production.example`: modelo de variaveis sem segredos reais.
- `deploy/nginx/lume.conf`: modelo de proxy reverso da VPS com HTTPS, static e media.
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
cp .env.production.example .env
```

Edite o arquivo:

```bash
nano .env
```

Troque obrigatoriamente:

- `SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `POSTGRES_PASSWORD`
- `EMAIL_HOST_PASSWORD`
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
/etc/nginx/certs/fullchain.pem
/etc/nginx/certs/privkey.pem
```

Pode ser certificado de origem do Cloudflare ou certificado emitido por Let's Encrypt. Nao versione esses arquivos.

## 4. Subir producao

Validar a configuracao renderizada:

```bash
docker compose -f docker-compose.prod.yml config
```

Subir:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Ver status:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web
```

O servico `web` roda `collectstatic`, `migrate` e `ensure_maintenance_user` antes de iniciar o Gunicorn. O `worker` espera o `web` ficar saudavel e nao roda migracoes por padrao, evitando corrida de migracoes. Se um dia for necessario permitir migracao pelo worker em ambiente controlado, use `LUME_WORKER_RUN_MIGRATIONS=True`.

O `.env.production.example` tambem declara `STATIC_ROOT=/app/staticfiles` e `MEDIA_ROOT=/app/media`, que combinam com os volumes persistentes do Compose.

## 5. Nginx na VPS

O Compose publica o Django apenas em:

```text
127.0.0.1:8000
```

Assim, o app nao fica exposto diretamente na internet. Instale o Nginx no host e use `deploy/nginx/lume.conf` como base.

Se o projeto estiver em outro caminho, ajuste:

```text
/srv/lume-gestao/data/staticfiles/
/srv/lume-gestao/data/media/
```

Depois copie a configuracao para o Nginx e recarregue:

```bash
sudo cp deploy/nginx/lume.conf /etc/nginx/sites-available/lume
sudo ln -s /etc/nginx/sites-available/lume /etc/nginx/sites-enabled/lume
sudo nginx -t
sudo systemctl reload nginx
```

## 6. Atualizar versao

Antes de atualizar:

```bash
sh scripts/backup-linux.sh
```

Depois:

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## 7. Backup

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

## 8. Restauracao

Em ambiente separado, com containers ligados:

```bash
cat backups/lume_db_YYYYMMDD_HHMMSS.sql | docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Restaurar media:

```bash
cat backups/lume_media_YYYYMMDD_HHMMSS.tar.gz | docker compose -f docker-compose.prod.yml exec -T web tar -xzf - -C /app
```

Teste restauracao antes de considerar o backup confiavel.

## 9. API mobile

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

## 10. Checklist antes de dados reais

- `docker compose -f docker-compose.prod.yml config` sem erros.
- `LUME_STRICT_PRODUCTION=True`.
- `LUME_SEED_DEMO=False`.
- HTTPS respondendo com certificado valido.
- Cloudflare em `Full (strict)`.
- Backup criado e restaurado em ambiente separado.
- Senhas padrao removidas.
- SMTP testado.
- WhatsApp em dry-run ate validacao final.
- Logs do `web`, `worker` e `nginx` sem erro recorrente.
