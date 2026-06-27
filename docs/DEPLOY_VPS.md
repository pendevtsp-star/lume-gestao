# Deploy VPS Linux

Guia de producao do Lume Gestao para VPS Linux com Docker Compose, PostgreSQL em container, Nginx, HTTPS com Certbot/Let's Encrypt e DNS pela Cloudflare.

Este guia considera desenvolvimento em Windows e producao em Ubuntu 24.04 LTS. Nao coloque senhas reais em arquivos versionados. O arquivo real `.env` deve existir apenas na VPS.

## 1. Pre-requisitos

- Repositorio no GitHub: `https://github.com/pendevtsp-star/lume-gestao.git`.
- Dominio gerenciado pela Cloudflare: `clinicafisiolume.com.br`.
- URL oficial do sistema: `https://sistema.clinicafisiolume.com.br`.
- VPS Ubuntu 24.04 LTS.
- Acesso SSH como usuario com `sudo`.
- Git instalado localmente no Windows para enviar atualizacoes.

Arquivos relevantes:

- `docker-compose.prod.yml`
- `.env.production.example`
- `deploy/nginx/lume.conf.example`
- `scripts/backup-production.sh`
- `scripts/restore-production.sh`
- `docs/UPDATE_PRODUCTION.md`
- `docs/SECURITY_PRODUCTION_CHECKLIST.md`

## 2. Compra/configuracao da VPS

Opcoes recomendadas para inicio:

- Hostinger KVM 2: simples para comecar, boa quando a prioridade e painel amigavel.
- Hetzner Cloud CX23: excelente custo-beneficio, boa para quem aceita configurar mais coisas manualmente.

Configure a VPS com:

- Ubuntu 24.04 LTS.
- Disco suficiente para banco, media e backups locais.
- Acesso SSH por chave quando possivel.
- Firewall liberando `22`, `80` e `443`.

## 3. Configuracao DNS no Cloudflare

No Cloudflare:

1. Crie um registro `A`.
2. Nome: `sistema`.
3. Conteudo: `IP_DA_VPS`.
4. Proxy: mantenha `DNS only` durante validacao e so depois ative `Proxied`.

Registro esperado:

```text
A sistema -> IP_DA_VPS
```

Nao coloque IP fixo no codigo ou em arquivos versionados; o IP fica apenas no DNS da Cloudflare.

Configuracao SSL/TLS recomendada:

- Antes do HTTPS estar pronto na VPS: mantenha o registro como `DNS only`.
- Depois do HTTPS validado na VPS: use modo `Full (strict)` e proxy ativo.
- Always Use HTTPS: ativo.
- Automatic HTTPS Rewrites: ativo.

Com `Full (strict)`, a VPS precisa ter certificado HTTPS valido. Use Certbot/Let's Encrypt ou Cloudflare Origin Certificate.

## 4. Primeiro acesso SSH

No Windows, use PowerShell ou Windows Terminal:

```powershell
ssh usuario@IP_DA_VPS
```

Atualize o sistema:

```bash
sudo apt update
sudo apt upgrade -y
```

Opcionalmente configure hostname:

```bash
sudo hostnamectl set-hostname lume-vps
```

## 5. Instalacao Docker

Em Ubuntu 24.04:

```bash
sudo apt install -y ca-certificates curl git ufw
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Saia e entre novamente no SSH. Teste:

```bash
docker --version
docker compose version
```

Firewall basico:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## 6. Clonagem do projeto

Use um caminho previsivel para combinar com o Nginx:

```bash
sudo mkdir -p /srv
sudo chown "$USER":"$USER" /srv
cd /srv
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd /srv/lume-gestao
```

Se estiver trabalhando na branch de deploy:

```bash
git checkout deploy/vps-production
```

## 7. Criacao do .env

Crie o `.env` real a partir do exemplo:

```bash
cp .env.production.example .env
nano .env
```

Troque obrigatoriamente:

- `SECRET_KEY`
- `ALLOWED_HOSTS=sistema.clinicafisiolume.com.br`
- `CSRF_TRUSTED_ORIGINS=https://sistema.clinicafisiolume.com.br`
- `PUBLIC_BASE_URL=https://sistema.clinicafisiolume.com.br`
- `LUME_HEALTHCHECK_HOST=sistema.clinicafisiolume.com.br`
- `POSTGRES_PASSWORD`
- `EMAIL_HOST_PASSWORD`
- credenciais Google e WhatsApp quando forem usadas

Nunca versionar o arquivo `.env` real. Ele deve existir somente na VPS.

Valores importantes para dados reais:

```text
ENVIRONMENT=production
DEBUG=False
LUME_STRICT_PRODUCTION=True
LUME_SEED_DEMO=False
WHATSAPP_DRY_RUN=True
```

Mantenha `WHATSAPP_DRY_RUN=True` ate validar numero, templates e permissao da Meta.

URLs publicas de integracao:

- Base publica do sistema: `https://sistema.clinicafisiolume.com.br`.
- Callback Google Agenda existente: `https://sistema.clinicafisiolume.com.br/integracoes/google/callback/`.
- Tela de integracoes existente: `https://sistema.clinicafisiolume.com.br/integracoes/`.
- O projeto ainda nao possui webhook publico versionado para WhatsApp/Meta; nao cadastre endpoints inventados.

## 8. Subida dos containers

Valide a configuracao:

```bash
docker compose -f docker-compose.prod.yml config
```

Suba os containers:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Veja status e logs:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f worker
```

O Compose publica a aplicacao apenas em `127.0.0.1:8000`, para que apenas o Nginx do host acesse o Gunicorn.

Healthcheck local:

```bash
curl http://127.0.0.1:8000/healthz/
```

Resposta esperada:

```json
{"status": "ok"}
```

## 9. Configuracao Nginx

Instale Nginx:

```bash
sudo apt install -y nginx
```

Copie o exemplo:

```bash
sudo cp deploy/nginx/lume.conf.example /etc/nginx/sites-available/lume
sudo nano /etc/nginx/sites-available/lume
```

No arquivo, confirme:

- `server_name sistema.clinicafisiolume.com.br;`
- `proxy_pass http://127.0.0.1:8000;`
- caminhos `/srv/lume-gestao/data/staticfiles/` e `/srv/lume-gestao/data/media/`

Ative:

```bash
sudo ln -s /etc/nginx/sites-available/lume /etc/nginx/sites-enabled/lume
sudo nginx -t
sudo systemctl reload nginx
```

## 10. HTTPS

Instale Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

Emita o certificado:

```bash
sudo certbot --nginx -d sistema.clinicafisiolume.com.br
```

Teste renovacao:

```bash
sudo certbot renew --dry-run
```

Depois de confirmar que o HTTPS responde corretamente na VPS, volte na Cloudflare, ative o proxy e configure SSL/TLS em `Full (strict)`.

Teste:

```bash
curl -I https://sistema.clinicafisiolume.com.br/healthz/
```

## 11. Criacao do superusuario

Crie o usuario administrador inicial:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

Use senha forte e nao reutilize credenciais de teste. Se usar usuario tecnico via `.env`, mantenha `LUME_MAINTENANCE_USER_ENABLED=False` para uso normal e ative apenas quando necessario.

## 12. Backup

Backup manual:

```bash
sh scripts/backup-production.sh
```

Variaveis opcionais:

```bash
BACKUP_DIR=/srv/lume-backups RETENTION_DAYS=30 sh scripts/backup-production.sh
```

O backup gera:

- `lume_db_YYYYMMDD_HHMMSS.sql`
- `lume_media_YYYYMMDD_HHMMSS.tar.gz`

Agendamento diario as 03:00:

```bash
crontab -e
```

Adicionar:

```text
0 3 * * * cd /srv/lume-gestao && sh scripts/backup-production.sh >> backups/backup.log 2>&1
```

Envie copia para fora da VPS. Exemplos:

```bash
rclone copy backups/ remote:lume-gestao/backups/
aws s3 sync backups/ s3://seu-bucket/lume-gestao/backups/
```

Nao considere backup confiavel antes de testar restauracao em ambiente separado.

## 13. Atualizacao de versao sem perder dados

O roteiro detalhado fica em `docs/UPDATE_PRODUCTION.md`.

Antes de atualizar:

```bash
sh scripts/backup-production.sh
```

Atualize:

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

Valide:

```bash
curl -I https://sistema.clinicafisiolume.com.br/healthz/
docker compose -f docker-compose.prod.yml logs --tail=80 web
```

Dados persistem em:

- volume Docker `postgres_data`
- diretorios `data/media`, `data/staticfiles`, `data/backups`

## 14. Rollback

Se uma atualizacao falhar:

1. Pare os containers:

```bash
docker compose -f docker-compose.prod.yml down
```

2. Volte para o commit/tag anterior:

```bash
git log --oneline -5
git checkout HASH_ANTERIOR
```

3. Suba novamente:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. Se houver corrupcao de dados, restaure backup em ambiente controlado:

```bash
sh scripts/restore-production.sh backups/lume_db_YYYYMMDD_HHMMSS.sql backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
```

A restauracao pede confirmacao digitando `RESTAURAR` para evitar sobrescrita acidental.

## 15. Checklist final

Use tambem o checklist dedicado em `docs/SECURITY_PRODUCTION_CHECKLIST.md`.

Antes de liberar usuarios reais:

- `.env` real criado na VPS e nao versionado.
- `DEBUG=False`.
- `LUME_STRICT_PRODUCTION=True`.
- `LUME_SEED_DEMO=False`.
- `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` com dominio real.
- DNS Cloudflare sem IP fixo no codigo; registro `A sistema -> IP_DA_VPS`.
- HTTPS ativo na VPS antes de ativar Cloudflare `Proxied` e `Full (strict)`.
- Cloudflare em `Full (strict)` apos validacao.
- HTTPS ativo com Certbot e `certbot renew --dry-run` aprovado.
- `/healthz/` respondendo HTTP 200.
- Nginx com `nginx -t` aprovado.
- Containers `db`, `web` e `worker` saudaveis.
- Superusuario criado com senha forte.
- SMTP testado.
- WhatsApp em `dry-run` ate validacao final.
- Backup manual gerado.
- Restauracao testada em ambiente separado.
- Rotina de backup automatico agendada.
- Procedimento de rollback conhecido.
