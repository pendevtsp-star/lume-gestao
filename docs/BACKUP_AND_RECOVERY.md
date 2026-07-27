# Backup e recuperacao

Este guia e um indice operacional seguro. Os scripts detalhados existentes
continuam sendo a fonte executavel; nenhum backup deve ser restaurado sem
janela de manutencao e validacao previa.

## O que deve ser preservado

- volume PostgreSQL `postgres_data`;
- `/srv/lume-gestao/.env`;
- `/srv/lume-gestao/data/media`;
- `/srv/lume-gestao/data/backups`;
- `/srv/lume-gestao/data/whatsapp-web`;
- compose de producao e identificadores das imagens ativas.

`data/staticfiles` pode ser reconstruido pela imagem, mas deve permanecer
intacto durante deploys normais para evitar indisponibilidade desnecessaria.

## Backup

Na VPS, use o script mantido pelo projeto:

```bash
cd /srv/lume-gestao
BACKUP_DIR=/srv/lume-gestao/data/backups ./scripts/backup-production.sh
```

Confirme arquivo, tamanho, data e log antes de considerar a copia valida. Para
copia fora da VPS e retencao, siga `docs/BACKUP_EXTERNO.md`.

## Recuperacao planejada

1. Registre imagens/commit em execucao e estado dos containers.
2. Interrompa escritas de forma controlada, sem remover volumes.
3. Confirme que o backup escolhido pertence ao ambiente correto.
4. Teste a restauracao em ambiente isolado sempre que possivel.
5. Execute o script com o caminho explicito do backup:

```bash
cd /srv/lume-gestao
./scripts/restore-production.sh \
  /srv/lume-gestao/data/backups/lume_db_YYYYMMDD_HHMMSS.sql \
  /srv/lume-gestao/data/backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
```

6. Aplique migrations somente se a imagem restaurada exigir.
7. Suba os containers sem `-v` e valide `db`, `web`, `worker` e
   `whatsapp-web`.
8. Valide `/healthz/`, login, agenda, pacientes, financeiro, midia e fila de
   mensagens antes de reabrir a operacao.

## Rollback de aplicacao

Rollback de imagem nao e restauracao de banco. O workflow de deploy registra
as imagens anteriores e tenta restaura-las quando a nova versao falha. Se uma
migration nao for retrocompativel, a decisao de restaurar banco exige backup
confirmado e intervencao manual.

## Proibicoes

- nao usar `docker compose down -v`;
- nao apagar `data/`, volumes ou `.env` durante deploy;
- nao sobrescrever backup valido com arquivo nao verificado;
- nao copiar dados reais para Git, artefatos publicos ou logs;
- nao declarar recuperacao concluida sem healthchecks e teste funcional.

Guias relacionados: `docs/DEPLOY_VPS.md`, `docs/UPDATE_PRODUCTION.md` e
`docs/SECURITY_PRODUCTION_CHECKLIST.md`.
