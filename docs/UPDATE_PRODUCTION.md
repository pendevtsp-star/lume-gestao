# Atualizacao de producao sem perder dados

Este roteiro atualiza o Lume Gestao na VPS preservando banco, arquivos de pacientes e backups.

## Regra de ouro

Nunca use em producao:

```bash
docker compose down -v
```

O `-v` remove volumes Docker e pode apagar o banco PostgreSQL. Use somente `up -d --build`, `restart` ou `down` sem `-v` quando realmente necessario.

## 1. Fazer backup antes

Entre na VPS:

```bash
ssh usuario@IP_DA_VPS
```

Entre na pasta do projeto:

```bash
cd /srv/lume-gestao
```

Rode backup:

```bash
sh scripts/backup-production.sh
```

Opcional:

```bash
BACKUP_DIR=/srv/lume-backups RETENTION_DAYS=30 sh scripts/backup-production.sh
```

Confirme que foram criados arquivos parecidos com:

```text
backups/lume_db_YYYYMMDD_HHMMSS.sql
backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
```

## 2. Verificar estado atual

```bash
git status
git rev-parse --short HEAD
docker compose -f docker-compose.prod.yml ps
curl -I https://sistema.clinicafisiolume.com.br/healthz/
```

Guarde o hash atual para rollback.

## 3. Atualizar codigo

```bash
git pull
```

Se o GitHub ainda nao estiver autenticado ou se for necessario subir direto da maquina de desenvolvimento, use o script via SSH na raiz do projeto:

```powershell
.\scripts\deploy-vps.ps1 -SshTarget "usuario@IP_DA_VPS"
```

Ele cria `dist\lume-gestao-vps.tar.gz`, envia para `/tmp` na VPS, exige que o `.env` real ja exista em `/srv/lume-gestao`, faz backup, extrai o codigo, roda `docker compose -f docker-compose.prod.yml up -d --build`, valida `/healthz/` e limpa cache antigo de build Docker.

Por padrao, apos o healthcheck passar, o script executa uma limpeza segura de cache de build:

```bash
docker builder prune -f --filter 'until=24h' --keep-storage '8GB'
```

Essa limpeza nao remove volumes, banco, media, containers em execucao ou imagens ativas. Ela reduz o acumulo em `/var/lib/containerd` e `/var/lib/docker` causado por builds repetidos. Para desativar em um deploy especifico:

```powershell
.\scripts\deploy-vps.ps1 -SshTarget "usuario@IP_DA_VPS" -SkipDockerBuildCachePrune
```

Para manter mais ou menos cache:

```powershell
.\scripts\deploy-vps.ps1 -SshTarget "usuario@IP_DA_VPS" -DockerBuildCacheKeepStorage "12GB" -DockerBuildCacheMinAge "48h"
```

Se estiver usando uma branch especifica:

```bash
git checkout deploy/vps-production
git pull
```

## 4. Validar configuracao antes de subir

```bash
docker compose -f docker-compose.prod.yml config
```

Quando aplicavel:

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py check --deploy
```

## 5. Rebuild e subida dos containers

Suba sem remover volumes:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Esse comando recria containers quando necessario, mas preserva:

- volume `postgres_data`;
- pasta `data/media`;
- pasta `data/staticfiles`;
- pasta `data/backups`;
- backups fora do projeto, se configurados.

## 6. Ver logs

```bash
docker compose -f docker-compose.prod.yml logs --tail=120 web
docker compose -f docker-compose.prod.yml logs --tail=120 worker
docker compose -f docker-compose.prod.yml ps
```

Procure erros de migracao, permissao de arquivo, conexao com banco ou variaveis ausentes.

## 7. Confirmar healthcheck

Local na VPS:

```bash
curl http://127.0.0.1:8000/healthz/
```

Publico via Nginx/HTTPS:

```bash
curl -I https://sistema.clinicafisiolume.com.br/healthz/
```

Esperado:

```text
HTTP/2 200
```

## 8. Confirmar banco e midia preservados

Banco:

```bash
docker compose -f docker-compose.prod.yml exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

Midia:

```bash
ls -lah data/media
docker compose -f docker-compose.prod.yml exec web sh -c 'ls -lah /app/media | head'
```

Static:

```bash
ls -lah data/staticfiles | head
```

## 9. Testes/checks quando aplicavel

Em atualizacoes maiores, rode:

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py check
docker compose -f docker-compose.prod.yml run --rm web python manage.py check --deploy
```

Se houver janela de manutencao e base pequena:

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py test
```

## 10. Rollback para commit anterior

Se a atualizacao falhar, volte ao hash salvo antes da atualizacao:

```bash
git checkout HASH_ANTERIOR
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs --tail=120 web
curl -I https://sistema.clinicafisiolume.com.br/healthz/
```

Se precisar voltar para a branch depois:

```bash
git checkout deploy/vps-production
```

## 11. Restaurar backup, se necessario

Use apenas quando houver problema real nos dados e preferencialmente apos testar em ambiente separado:

```bash
sh scripts/restore-production.sh backups/lume_db_YYYYMMDD_HHMMSS.sql backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
```

O script pede confirmacao digitando:

```text
RESTAURAR
```

## 12. Checklist pos-atualizacao

- [ ] Backup feito antes da atualizacao.
- [ ] `git pull` concluiu sem conflito.
- [ ] `docker compose -f docker-compose.prod.yml config` passou.
- [ ] `docker compose -f docker-compose.prod.yml up -d --build` executou sem erro.
- [ ] Limpeza de cache Docker pos-deploy executou ou foi conscientemente ignorada.
- [ ] Logs do `web` sem erro recorrente.
- [ ] Logs do `worker` sem erro recorrente.
- [ ] `/healthz/` responde HTTP 200.
- [ ] Login administrativo funciona.
- [ ] Agenda, pacientes e financeiro abrem normalmente.
- [ ] `data/media` continua presente.
- [ ] Banco PostgreSQL continua com tabelas e registros.
- [ ] Nunca foi usado `docker compose down -v`.
