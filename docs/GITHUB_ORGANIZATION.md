# Organizacao GitHub

Este repositorio atende um sistema em producao com dados reais. O GitHub deve refletir com clareza o que esta em producao, o que esta em revisao e o que ja pode ser arquivado.

## Branches

- `main`: linha principal do projeto e origem do deploy de producao.
- `codex/<tema-curto>`: branches temporarias de trabalho, sempre com escopo pequeno.
- `chore/<tema-curto>`: ajustes documentais, organizacionais ou operacionais sem mudanca funcional.

## Regras

- Como ha um unico desenvolvedor no momento, a rotina prioritaria e trabalhar em `main` com commits pequenos e validaveis.
- Branch dedicada continua recomendada para mudancas grandes, experimentais, arriscadas ou quando houver revisao por PR.
- Branch temporaria deve ser removida depois que o conteudo estiver incorporado ao deploy ou arquivado em outra branch de referencia.
- Nao deixar branches antigas abertas apenas como memoria. O historico do Git preserva commits incorporados.
- Antes de apagar branch remota, confirmar que:
  - o commit da branch esta contido em `main`, ou
  - o trabalho foi substituido por outra branch/PR, ou
  - o usuario autorizou arquivar/remover a linha de trabalho.

## Producao

- O deploy de producao parte de `main` pelo GitHub Actions.
- A VPS em operacao nao deve depender de checkout Git local. Ela consome imagens imutaveis publicadas no GHCR.
- O diretorio `/srv/lume-gestao` guarda `docker-compose.prod.yml`, `.env` real e dados persistentes da producao.
- `.env`, `data`, `media`, backups e volumes pertencem exclusivamente a VPS e nunca devem ser versionados.
- Nunca usar force-push em branch de producao sem plano de rollback e autorizacao explicita.

## Revisao rapida antes de trabalhar

1. `git fetch --all --prune --tags`
2. `git status --short --branch`
3. `git branch -r --sort=-committerdate`
4. Comparar branches ativas com `main`.
5. Confirmar healthcheck, imagens e commit publicado quando a tarefa envolver producao.

## Limpeza recomendada

Branches ja incorporadas a `main` devem ser candidatas a remocao remota depois de confirmacao. Branches com trabalho unico devem virar PR, ser agrupadas em uma branch de estabilizacao ou ser preservadas explicitamente.

## Aplicativo mobile

`apps/lume_app/` e o cliente Flutter futuro para Android/iOS. O projeto esta pausado temporariamente e deve permanecer versionado, mas fora do deploy web e dos workflows obrigatorios ate ser retomado.
