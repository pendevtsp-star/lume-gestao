# Production Guardrails

Este projeto esta em producao com dados reais da clinica em `sistema.clinicafisiolume.com.br`.

## Regras obrigatorias

- `main` e a linha principal de trabalho e producao.
- Como ha um unico desenvolvedor no momento, commits diretos em `main` sao permitidos quando o usuario autorizar explicitamente commit/push/deploy.
- Use branch dedicada apenas para mudancas longas, experimentais, arriscadas ou quando o usuario pedir PR.
- Antes de qualquer deploy em producao, faca backup validado do banco de dados e dos arquivos de midia.
- Nunca execute `docker compose down -v` em producao.
- Trate migrations com cuidado especial. Avalie risco de perda de dados, locks, reversibilidade e impacto em dados reais antes de aplicar.
- Rode testes antes de abrir PR:
  - `python manage.py check`
  - `python manage.py test`
- Prefira mudancas pequenas, incrementais e reversiveis.
- Nunca proponha limpeza ampla, refatoracao grande ou reorganizacao estrutural sem uma analise previa somente leitura.
- Em atualizacoes na VPS, envie e mantenha somente os arquivos necessarios para o deploy; nao deixe pacotes temporarios, patches, logs ou diretorios duplicados acumulados fora dos locais definidos.

## Areas com revisao especial

Mudancas nas areas abaixo exigem revisao cuidadosa de seguranca, dados e comportamento:

- autenticacao
- permissoes
- prontuario
- financeiro
- agenda
- WhatsApp
- Google Calendar
- API mobile
- dados sensiveis
- deploy
- backups

## Conduta esperada do Codex

- Confirmar o escopo antes de tocar arquivos sensiveis.
- Separar mudancas documentais, funcionais e de infraestrutura.
- Evitar alteracoes oportunistas fora do pedido.
- Nao executar deploy, comandos destrutivos ou scripts de migracao em producao sem autorizacao explicita.
- Preservar dados reais como prioridade maxima.
- Antes de limpar branches ou reorganizar GitHub, comparar branches `codex/*`, commits remotos e o commit real da VPS; nao usar force-push em producao sem autorizacao explicita.
