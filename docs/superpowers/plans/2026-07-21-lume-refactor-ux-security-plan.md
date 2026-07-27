# Lume Refactor, UX and Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o Lume localmente para uma base mais organizada, segura, consistente e profissional sem quebrar os fluxos que ja operam com dados reais.

**Architecture:** A implementacao sera incremental, com o backend Django permanecendo como fonte da verdade. Primeiro criamos uma linha de base verificavel; depois separamos responsabilidades dos modulos grandes, consolidamos o design system e refinamos os fluxos por prioridade operacional. Cada fase termina com testes automatizados, verificacao mobile/desktop e aprovacao do usuario antes da fase seguinte.

**Tech Stack:** Django, templates Django, CSS/JavaScript, SQLite para testes locais isolados, Docker Compose, WhatsApp Web gateway, PWA, GitHub Actions.

## Global Constraints

- Trabalhar apenas no repositorio canonico `C:\Users\maxue\projetos_programacao\lume_project`.
- Nao alterar dados reais, `.env`, `db.sqlite3`, `media`, volumes, backups ou credenciais.
- Nao fazer push, acionar GitHub Actions ou fazer deploy antes da aprovacao local do usuario.
- Preservar as automacoes existentes de agendamento, sessao proxima, aniversario e cobranca.
- Manter WhatsApp Web como unico provedor operacional; codigo Meta legado so pode ser removido apos prova de que nao possui consumidor ativo.
- Preservar compatibilidade de URLs e comportamento durante a refatoracao.
- Usar testes de regressao antes de corrigir regras de negocio.
- Validar desktop e mobile reais em cada fase visual.
- O aplicativo Flutter em `apps/lume_app` permanece pausado e fora dos checks padrao, salvo mudanca explicita nesse caminho.

---

## Fase 0: Linha de base e mapa de risco

**Objetivo:** congelar uma referencia local confiavel antes de qualquer refatoracao.

**Arquivos principais:** `README.md`, `PRODUCT.md`, `DESIGN.md`, `config/settings.py`, `.github/workflows/*.yml`, testes de cada app.

- [ ] Registrar branch, commit, migrations, dependencias e estado limpo do repositorio.
- [ ] Executar `python manage.py check`, `python manage.py makemigrations --check --dry-run` e a suite de testes completa em banco local isolado.
- [ ] Inventariar URLs, views, templates, modelos, comandos e integrações por dominio.
- [ ] Criar uma matriz de fluxos criticos: login, agenda, reagendamento, pacientes, recebimentos, WhatsApp, Lume em Casa, checkout e landing.
- [ ] Registrar capturas desktop e mobile dos fluxos criticos para comparacao posterior.
- [ ] Rodar CodeRabbit quando o CLI estiver instalado e autenticado; registrar separadamente qualquer bloqueio da ferramenta.

**Gate de aceite:** linha de base documentada, testes conhecidos e nenhum arquivo de producao alterado.

## Fase 1: Correcoes criticas e protecao contra regressao

**Objetivo:** estabilizar os comportamentos que afetam diretamente a operacao antes de mover codigo.

**Arquivos principais:** `scheduling/slots.py`, `scheduling/services.py`, `scheduling/views.py`, `scheduling/tests.py`, `core/services/whatsapp_automation.py`, `core/management/commands/process_whatsapp_queue.py`, `core/tests.py`.

- [ ] Consolidar regressões de disponibilidade, vaga em turma existente, reagendamento individual e recorrencia.
- [ ] Cobrir idempotencia de mensagens, reprocessamento da fila e protecao contra envio duplicado.
- [ ] Cobrir aniversarios, cobrancas e lembretes de 24 horas e 1 hora em limites de data/hora.
- [ ] Padronizar erros de regra de negocio para que a UI mostre a causa real e uma acao de recuperacao.
- [ ] Validar que o gateway WhatsApp Web indisponivel nao duplica nem perde mensagens silenciosamente.

**Gate de aceite:** testes de regressao verdes e simulacao local dos fluxos criticos aprovada.

## Fase 2: Refatoracao estrutural incremental

**Objetivo:** reduzir arquivos grandes e responsabilidades misturadas sem reescrever o sistema.

**Arquivos principais:** `scheduling/views.py`, `core/views.py`, `reports/views.py`, `billing/views.py`, `patients/views.py`, novos modulos `services.py`, `selectors.py` e pacotes de views quando necessarios.

- [ ] Separar consultas de leitura em selectors e regras de alteracao em services.
- [ ] Dividir `scheduling/views.py` por agenda, reagendamento, presenca e notificacoes.
- [ ] Dividir `core/views.py` por dashboard, configuracoes e integrações.
- [ ] Dividir `reports/views.py` por relatorio e mover calculos para services/selectors testaveis.
- [ ] Remover duplicacao de validacao e formatacao entre views, forms e templates.
- [ ] Manter nomes de URL e contratos existentes para evitar regressao de navegacao.

**Gate de aceite:** reducao mensuravel dos arquivos monoliticos, cobertura preservada e URLs inalteradas.

## Fase 3: Fundacao visual e responsiva

**Objetivo:** criar uma linguagem visual unica antes de redesenhar paginas individualmente.

**Arquivos principais:** `DESIGN.md`, `templates/base.html`, `templates/base_public.html`, `static/css/app.css`, `static/css/website.css`, `static/js/app.js`, partials compartilhados em `templates/components/`.

- [ ] Consolidar tokens de cor, tipografia, espacamento, borda, sombra e estados de foco.
- [ ] Criar componentes reutilizaveis para cabecalho, filtros, tabelas, formulario, estado vazio, alerta, modal e barra de acoes.
- [ ] Corrigir o shell mobile: menu em drawer, conteudo com largura total e barra fixa sem cobrir informacoes.
- [ ] Definir breakpoints e dimensoes estaveis para desktop, tablet e celular.
- [ ] Padronizar estados de carregamento, sucesso, erro, vazio, desabilitado e offline.
- [ ] Garantir navegacao por teclado, foco visivel, labels e contraste.

**Gate de aceite:** pagina de demonstracao dos componentes aprovada em desktop e mobile antes da migracao em massa.

## Fase 4: Fluxos operacionais prioritarios

**Objetivo:** aplicar o novo sistema visual aos fluxos mais usados e simplificar a operacao diaria.

**Arquivos principais:** `templates/core/dashboard.html`, `templates/scheduling/*.html`, `templates/patients/*.html`, `templates/billing/*.html`, JavaScript e CSS associados.

- [ ] Dashboard: priorizar agenda do dia, pendencias e acoes imediatas; remover metricas sem decisao associada.
- [ ] Agenda: compactar filtros, reduzir espaco vazio e manter navegacao semanal legivel no celular.
- [ ] Sessao em grupo: substituir menus que escapam do modal por painel de acoes acessivel e rolavel.
- [ ] Reagendamento: manter paciente, origem, destino e vagas visiveis durante todo o fluxo.
- [ ] Pacientes: busca persistente, acoes por linha e resumo clinico-operacional claro.
- [ ] Financeiro: unificar conceitos de receber, mensalidades, inadimplencia e cobrancas em uma arquitetura compreensivel.
- [ ] Formularios: agrupar campos por tarefa, mostrar validacao junto ao campo e manter acao primaria previsivel.

**Gate de aceite:** jornada completa de agenda, paciente e recebimento aprovada em desktop e mobile.

## Fase 5: Mensagens, automacoes e integrações

**Objetivo:** tornar WhatsApp e automacoes simples de entender e seguras para operar.

**Arquivos principais:** `core/services/whatsapp_automation.py`, `core/models.py`, `core/forms.py`, `templates/core/integrations.html`, `templates/core/message_automation.html`, `whatsapp-web-gateway/src/server.js`.

- [ ] Mostrar uma unica jornada de WhatsApp Web: QR, conectando, conectado, desconectado e erro recuperavel.
- [ ] Separar configuracao da conexao, modelos de mensagem, regras de automacao e fila operacional.
- [ ] Permitir editar mensagens com variaveis documentadas, previa e validacao antes de salvar.
- [ ] Exibir proxima execucao, ultimo envio, falhas e tentativa seguinte de cada regra.
- [ ] Manter Google Agenda como recurso futuro claramente inativo, sem competir visualmente com o WhatsApp.
- [ ] Identificar e isolar o legado Meta; remover somente apos busca de referencias, testes e migracao de dados necessaria.

**Gate de aceite:** QR funcional, estado coerente e simulacao das quatro automacoes sem duplicidade.

## Fase 6: Modulos secundarios e landing

**Objetivo:** levar a mesma qualidade aos modulos menos frequentes sem deixar ilhas visuais ou funcionais.

**Arquivos principais:** `templates/reports/`, `templates/homecare/`, `templates/lume_connect/`, `templates/team/`, `templates/accounts/`, `templates/checkout/`, `website/templates/website/home.html`, `static/css/website.css`.

- [ ] Revisar relatorios para responder perguntas de negocio e permitir exportacao clara.
- [ ] Revisar Lume em Casa e Lume Connect com fluxos de acesso, progresso, midia e estados vazios consistentes.
- [ ] Revisar equipe e configuracoes administrativas para reduzir opcoes soltas.
- [ ] Revisar checkout e Asaas mantendo recursos dependentes de credenciais em estado explicitamente indisponivel.
- [ ] Harmonizar landing com o design aprovado, dados reais do admin e comportamento mobile.
- [ ] Remover ou remodelar paginas sem dono, sem entrada navegavel ou sem resultado operacional util.

**Gate de aceite:** nenhum modulo ativo usa layout legado ou acao sem destino claro.

## Fase 7: Seguranca e privacidade

**Objetivo:** endurecer controles de acesso e superficies externas sem alterar dados de producao.

**Arquivos principais:** `config/settings.py`, `core/middleware.py`, `core/api_permissions.py`, APIs de cada app, uploads, webhooks, comandos e testes de seguranca.

- [ ] Auditar autorizacao por objeto e impedir acesso baseado apenas em ID previsivel.
- [ ] Revisar CSRF, CORS, cookies, cabecalhos, hosts, redirecionamentos e configuracao por ambiente.
- [ ] Aplicar rate limiting em login, webhooks, checkout, uploads e endpoints de automacao.
- [ ] Validar tipo, tamanho e armazenamento de uploads e midias.
- [ ] Restringir subprocessos e comandos externos com argumentos permitidos e timeouts.
- [ ] Garantir que PWA nao armazene paginas autenticadas, dados clinicos ou respostas sensiveis em cache.
- [ ] Expandir trilha de auditoria para alteracoes financeiras, agenda, permissoes e integrações.

**Gate de aceite:** testes negativos de permissao passam e scans locais nao apontam vulnerabilidade alta conhecida sem tratamento.

## Fase 8: PWA, desempenho e confiabilidade

**Objetivo:** tornar a experiencia instalavel e resiliente sem comprometer dados sensiveis.

**Arquivos principais:** manifest, service worker, `templates/base.html`, assets estaticos, configuracao de cache e testes de navegador.

- [ ] Validar manifest, icones, installability e atualizacao de versao.
- [ ] Limitar cache offline a shell e assets publicos; rotas autenticadas usam rede e nunca persistem respostas clinicas.
- [ ] Reduzir CSS/JS duplicado, imagens excessivas e recursos bloqueantes.
- [ ] Verificar navegacao em conexao lenta e tratamento de falha de rede.
- [ ] Medir acessibilidade, layout shift e desempenho nas paginas criticas.

**Gate de aceite:** PWA instalavel, atualizavel e sem vazamento de conteudo autenticado pelo cache.

## Fase 9: Qualidade, CI e documentacao

**Objetivo:** transformar as garantias locais em gates simples e confiaveis antes de publicar.

**Arquivos principais:** `.github/workflows/*.yml`, `README.md`, `docs/*.md`, exemplos de ambiente e scripts de verificacao.

- [ ] Eliminar jobs duplicados entre CI, coverage e seguranca.
- [ ] Manter testes Django, migration check, static checks e scans de seguranca como gates claros.
- [ ] Executar checks do app Flutter somente quando `apps/lume_app/**` mudar.
- [ ] Documentar comandos locais, arquitetura, integrações, backup e recuperacao.
- [ ] Atualizar inventario de funcionalidades ativas, pausadas e futuras.
- [ ] Rodar CodeRabbit no diff completo quando o CLI estiver disponivel e autenticado.

**Gate de aceite:** pipeline reproduz os checks locais e documentacao descreve o sistema realmente entregue.

## Fase 10: Homologacao local e decisao de publicacao

**Objetivo:** obter aprovacao final antes de qualquer alteracao remota.

- [ ] Executar suite completa, migration check e verificacoes de seguranca.
- [ ] Rodar roteiro manual com perfis admin, profissional e paciente.
- [ ] Capturar comparativos desktop/mobile das paginas criticas.
- [ ] Verificar console, requests, PWA, acessibilidade e responsividade.
- [ ] Entregar resumo de mudancas, riscos residuais e itens adiados.
- [ ] Aguardar aprovacao explicita do usuario.

**Fora deste plano local:** commit final, push para `main`, GitHub Actions e deploy na VPS. Esses passos formam um plano de release separado e so podem ocorrer apos aprovacao.

## Ordem recomendada de execucao

1. Fase 0.
2. Fase 1.
3. Fase 2.
4. Fase 3.
5. Fase 4.
6. Fase 5.
7. Fase 6.
8. Fase 7.
9. Fase 8.
10. Fase 9.
11. Fase 10.

## Estrategia de controle

- Cada fase e executada em lote proprio e termina com relatorio de arquivos alterados e testes.
- Mudancas de schema recebem migration e teste de migracao no mesmo lote.
- Mudancas visuais recebem capturas desktop e mobile antes de avancar.
- Correcao de bug comeca por teste reproduzindo a falha.
- Refatoracao sem mudanca funcional e separada de redesign para facilitar diagnostico.
- Nenhuma fase posterior serve para esconder falha de uma fase anterior.
