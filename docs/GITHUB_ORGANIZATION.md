# Organizacao GitHub

Este repositorio atende um sistema em producao com dados reais. O GitHub deve refletir com clareza o que esta em producao, o que esta em revisao e o que ja pode ser arquivado.

## Branches

- `main`: linha historica/base do projeto. Nao usar para alteracoes diretas de producao.
- `deploy/vps-production`: branch de referencia para producao.
- `codex/<tema-curto>`: branches temporarias de trabalho, sempre com escopo pequeno.
- `chore/<tema-curto>`: ajustes documentais, organizacionais ou operacionais sem mudanca funcional.

## Regras

- Nao fazer alteracoes diretas na `main`.
- Toda mudanca funcional deve sair de branch dedicada e passar por PR antes de entrar na branch de deploy.
- Branch temporaria deve ser removida depois que o conteudo estiver incorporado ao deploy ou arquivado em outra branch de referencia.
- Nao deixar branches antigas abertas apenas como memoria. O historico do Git preserva commits incorporados.
- Antes de apagar branch remota, confirmar que:
  - o commit da branch esta contido em `deploy/vps-production`, ou
  - o trabalho foi substituido por outra branch/PR, ou
  - o usuario autorizou arquivar/remover a linha de trabalho.

## Producao

- A VPS em operacao deve ser comparada com o GitHub antes de qualquer deploy.
- Se a VPS estiver em commit diferente da branch remota, primeiro classificar:
  - mesmo conteudo com hash diferente: registrar e alinhar no proximo deploy controlado;
  - conteudo diferente: preservar o commit em branch remota antes de qualquer mudanca.
- Nunca usar force-push em branch de producao sem plano de rollback e autorizacao explicita.

## Revisao rapida antes de trabalhar

1. `git fetch --all --prune --tags`
2. `git status --short --branch`
3. `git branch -r --sort=-committerdate`
4. Comparar branches ativas com `deploy/vps-production`.
5. Confirmar healthcheck e commit da VPS quando a tarefa envolver producao.

## Limpeza recomendada

Branches ja incorporadas ao deploy devem ser candidatas a remocao remota depois de confirmacao. Branches com trabalho unico devem virar PR ou ser agrupadas em uma branch de estabilizacao.
