# Handoff - Lume Gestao - Deploy VPS

Data: 2026-06-27

## Contexto geral

Projeto: `lume-gestao`

Branch de producao preparada: `deploy/vps-production`

Repositorio: `https://github.com/pendevtsp-star/lume-gestao`

Dominio principal: `clinicafisiolume.com.br`

URL publica do sistema: `https://sistema.clinicafisiolume.com.br`

VPS Ubuntu: `187.127.37.208`

## Estado atual do Git

Branch local e remota alinhadas em `deploy/vps-production`.

Ultimos commits importantes enviados ao GitHub:

- `e5d20af Configura dominio real para deploy VPS`
- `1b4710c Corrige healthcheck em producao`
- `744fd6e Normaliza finais de linha em arquivos Python`

Nao ha alteracoes locais pendentes no workspace Windows no momento da conclusao do deploy.

## O que foi feito nesta conversa

- Atualizado `.env.production.example` com o dominio real `sistema.clinicafisiolume.com.br`.
- Adicionado `PUBLIC_BASE_URL=https://sistema.clinicafisiolume.com.br`.
- Adicionado `LUME_HEALTHCHECK_HOST=sistema.clinicafisiolume.com.br`.
- Validado que `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, HTTPS, HSTS, proxy SSL e REST continuam configuraveis via ambiente.
- Atualizado `deploy/nginx/lume.conf.example` com dominio real e comentarios de Cloudflare/Certbot.
- Atualizadas documentacoes de deploy, seguranca, Google Agenda, WhatsApp, SMTP e atualizacao de producao.
- Ajustado o healthcheck do Docker de producao para enviar o cabecalho `Host` correto, sem precisar abrir `ALLOWED_HOSTS` para `127.0.0.1`.
- Corrigida normalizacao de finais de linha em `accounts/views.py` e `team/models.py`.

## O que foi feito na VPS

- Acesso SSH configurado com chave local do Codex:
  - chave publica adicionada em `/root/.ssh/authorized_keys`.
- Instalados/validados:
  - Docker CE
  - Docker Compose plugin
  - Git
  - Nginx
  - Certbot
  - plugin Certbot Nginx
- Projeto clonado em `/srv/lume-gestao`.
- Branch ativa na VPS: `deploy/vps-production`.
- Criado `.env` real na VPS a partir de `.env.production.example`.
- Gerados automaticamente:
  - `SECRET_KEY`
  - `POSTGRES_PASSWORD`
- Criados diretorios persistentes:
  - `/srv/lume-gestao/data/media`
  - `/srv/lume-gestao/data/staticfiles`
  - `/srv/lume-gestao/data/backups`
- Subidos containers de producao:
  - `lume-gestao-db-1`
  - `lume-gestao-web-1`
  - `lume-gestao-worker-1`
- Rodaram migracoes iniciais do banco.
- `collectstatic` executado.
- Criado superusuario `admin`.
- Senha temporaria do admin salva somente na VPS:
  - `/root/lume-admin-password.txt`
- Configurado Nginx para `sistema.clinicafisiolume.com.br`.
- Emitido certificado Let's Encrypt.
- HTTPS ativado.
- Certbot renew dry-run aprovado.
- Firewall UFW ativado com:
  - SSH `22`
  - HTTP `80`
  - HTTPS `443`
- Backup inicial criado em:
  - `/srv/lume-gestao/data/backups`
- Rotina diaria de backup criada:
  - `/etc/cron.d/lume-backup`
  - horario: `03:15`
  - retencao: 14 dias

## Validacoes realizadas

- `https://sistema.clinicafisiolume.com.br/healthz/` retorna `{"status": "ok"}`.
- `https://sistema.clinicafisiolume.com.br/login/` retorna HTTP 200.
- `docker compose -f docker-compose.prod.yml ps` mostra `db` e `web` saudaveis.
- `worker` esta ativo e processando fila do WhatsApp.
- `nginx -t` passou.
- `certbot renew --dry-run --no-random-sleep-on-renew` passou.
- `python manage.py check --deploy` passou com apenas aviso de `SECURE_HSTS_PRELOAD=False`.

## Observacoes importantes

- `SECURE_HSTS_PRELOAD=False` foi mantido de forma proposital no beta. Isso evita travar o dominio em preload antes da versao estabilizar.
- Cloudflare pode ser configurado como `Proxied` e SSL/TLS `Full strict`, pois o HTTPS na VPS ja esta funcionando.
- O arquivo `.env` real nao foi versionado e deve permanecer somente na VPS.
- A senha temporaria do admin nao foi exposta no chat. Para consultar:

```bash
cat /root/lume-admin-password.txt
```

Depois do primeiro login, trocar a senha do usuario `admin`.

## Migracao dos dados locais da clinica

A irma do usuario havia preenchido dados reais em uma instalacao Docker local Linux antes da VPS ficar pronta.

Esses dados foram migrados para a VPS com o seguinte fluxo:

1. Foi gerada chave SSH no notebook Linux da clinica.
2. A chave publica foi autorizada na VPS em `/root/.ssh/authorized_keys`.
3. Foram enviados para a VPS:
   - `/srv/lume-gestao/data/backups/lume_local_db.sql`
   - `/srv/lume-gestao/data/backups/lume_local_media.tar.gz`
4. Foi feito backup da VPS antes da restauracao:
   - `/srv/lume-gestao/data/backups/lume_db_20260627_235946.sql`
   - `/srv/lume-gestao/data/backups/lume_media_20260627_235946.tar.gz`
5. `web` e `worker` foram parados.
6. O banco da VPS foi recriado.
7. O dump local foi importado.
8. A pasta `media` foi restaurada. O arquivo de media tinha 45 bytes e estava vazio, indicando que nao havia uploads/fotos para migrar.
9. Os containers foram recriados.
10. `migrate`, `check` e `check --deploy` foram executados.

Resultado da validacao apos migracao:

- usuarios: 5
- pacientes: 41
- profissionais: 3
- funcionarios: 2
- agendamentos: 10
- pacotes: 3
- matriculas/mensalidades: 4
- pagamentos: 4
- cobrancas: 2
- despesas: 2

Usuarios encontrados:

- `marina`
- `helena`
- `recepcao`
- `thaissimoesfisio`
- `admin` com `is_staff=True` e `is_superuser=True`

## Ponto onde paramos

O sistema esta online em producao com os dados locais da clinica migrados para a VPS.

URL de producao:

```text
https://sistema.clinicafisiolume.com.br
```

Healthcheck:

```text
https://sistema.clinicafisiolume.com.br/healthz/
```

Status pos-migracao:

- `db`: saudavel
- `web`: saudavel
- `worker`: ativo
- login: respondendo HTTP 200
- migracoes: sem pendencias
- `python manage.py check`: sem problemas
- `python manage.py check --deploy`: apenas aviso esperado de `SECURE_HSTS_PRELOAD=False`

Proximos passos recomendados:

1. Entrar no sistema em producao com os usuarios migrados e validar visualmente pacientes, agenda e financeiro.
2. Trocar senhas padrao/de teste.
3. Confirmar com a clinica que, a partir de agora, todos devem usar somente a URL da VPS.
4. Manter o notebook local apenas como referencia temporaria, sem novos cadastros.
5. Fazer novo backup depois da validacao manual.

O roteiro de migracao permanece documentado em `docs/MIGRACAO_DADOS_LOCAL_PARA_VPS.md`.
