# Plano de acao produto, UX e integracoes

Atualizado em: 2026-07-12

Este documento organiza os proximos blocos de evolucao do Lume Gestao, da landing page e do Lume em casa. A regra combinada e que cada ciclo de mudanca seja robusto: nenhum bloco deve ser executado com menos de 10 atualizacoes planejadas, para evitar entregas pequenas, soltas e dificeis de validar.

## Direcao geral

Prioridade do produto:

1. estabilizar a operacao real da clinica;
2. reduzir atrito de agenda, presenca, pagamentos e comunicacao;
3. preparar o sistema para uso mobile/PWA;
4. concluir checkout Asaas dentro do sistema;
5. criar dados clinicos simples para acompanhar evolucao do paciente;
6. manter o caminho oficial de integracoes, mas com UX muito mais guiada.

## Analise dos pedidos novos

### PWA

O PWA deve ser tratado como uma camada do sistema web atual, nao como um app paralelo. A melhor abordagem e adicionar manifesto, service worker, icones, tela instalavel, cache controlado e experiencia mobile mais confiavel. Por seguranca, paginas com dados sensiveis nao devem ficar disponiveis offline com conteudo clinico ou financeiro em cache. O offline deve priorizar shell, assets, pagina de erro amigavel e talvez atalhos de leitura sem dados privados.

### Checkout Asaas direto no sistema

O projeto ja possui base de checkout, pedidos, conta recebedora, webhooks e homologacao dry-run/sandbox. O melhor caminho agora e finalizar o fluxo comercial de ponta a ponta:

- paciente logado paga mensalidade pendente;
- comprador novo compra plano publico;
- gestao acompanha pedido e baixa automatica;
- Asaas recebe pagamento via Pix, boleto ou cartao;
- webhook confirmado libera acesso, pacote, mensalidade ou assinatura;
- producao fica protegida por flags e validacao de token.

Para a clinica atual, a forma mais simples e usar a conta Asaas da propria clinica. Para SaaS futuro, o desenho deve continuar preparado para conta plataforma, subcontas e split.

### Solicitacao de remarcacao

A remarcacao deve ser um pedido do paciente, nao uma alteracao direta. O paciente solicita, a equipe aprova ou recusa, o sistema registra motivo, horario original, novo horario desejado e historico. Isso preserva controle da agenda e evita bagunca em turmas com mais de um aluno.

### Aviso de faltas com antecedencia

O sistema deve atuar antes da falta acontecer: lembrete da aula, pedido de confirmacao e alerta quando o paciente tem historico de ausencia ou quando a turma depende de confirmacao. A regra precisa permitir canal WhatsApp, PWA e painel interno.

### Historico de presenca

Presenca deve virar dado central. Cada aula precisa registrar status: presente, falta, falta justificada, reagendada, cancelada pela clinica e reposicao. Esse historico alimenta relatorios, renovacao, frequencia, credito e evolucao.

### Metas, conquistas e evolucao

As metas devem nascer de uma avaliacao simples e serem acompanhadas por check-ins curtos. Conquistas podem ser marcos manuais ou automaticos, como frequencia mantida, dor reduzida, meta concluida, retorno apos pausa ou plano renovado.

### Notificacao da aula no dia

Deve existir regra de lembrete no dia da aula, com horario configuravel. Para evitar excesso de mensagem, o sistema deve controlar envio unico por aula, logs, opt-in e fallback para painel quando WhatsApp nao estiver disponivel.

### Aviso de renovacao do plano

O sistema ja tem financeiro e planos. Falta transformar renovacao em fluxo ativo: detectar vencimento, avisar paciente e equipe, oferecer checkout, registrar tentativa de cobranca e apontar risco de interrupcao.

### Feriados e mudancas de horario

Criar calendario operacional da clinica. Feriados, recesso e mudancas especiais devem afetar agenda, lembretes e notificacoes. O ideal e permitir comunicado em massa para pacientes afetados.

### Programa de indicacao

Comecar simples: codigo/link de indicacao por paciente, registro do indicado, status de conversao e beneficio manual ou automatico. Depois pode evoluir para cashback, desconto ou bonus de aulas.

### Avaliacao rapida e check-in

Criar formulario curto com:

- quais seus objetivos;
- queixa principal;
- metas;
- como voce esta se sentindo hoje;
- sem dor, dor leve, dor moderada, dor intensa;
- observacao opcional.

Isso cria dados comparaveis sem virar prontuario pesado.

### Relatorio mensal

Relatorio mensal deve resumir aulas feitas, frequencia, faltas, evolucao de dor, metas, conquistas e recomendacao da equipe. Ele pode ser interno primeiro e depois ganhar versao compartilhavel com o paciente.

## Bloco 1 - Base mobile, PWA e consistencia operacional

Objetivo: deixar o sistema mais confiavel no celular e instalavel como PWA, sem comprometer dados sensiveis.

Atualizacoes minimas do bloco:

1. Criar `manifest.webmanifest` com nome, icones, tema, start_url e display standalone.
2. Adicionar rota segura para servir o manifesto no Django.
3. Criar service worker com cache apenas de assets estaticos e pagina offline neutra.
4. Evitar cache de paginas autenticadas com dados clinicos, financeiros ou pessoais.
5. Adicionar icones PWA em tamanhos adequados para Android, iOS e desktop.
6. Ajustar `base.html` para registrar manifesto, theme-color e metatags mobile.
7. Criar tela offline simples com mensagem clara e botao para tentar novamente.
8. Melhorar layout mobile do shell principal, menu lateral e acoes fixas.
9. Padronizar estados de loading, erro, sucesso e vazio em componentes recorrentes.
10. Criar checklist de QA PWA: instalar, abrir standalone, navegar, recarregar, perder conexao e voltar.
11. Adicionar testes de headers para paginas sensiveis nao ficarem cacheadas indevidamente.
12. Documentar limitacoes do offline para equipe e gestao.

Criterio de pronto: sistema instalavel no celular, sem expor dados sensiveis offline, com navegacao mobile mais previsivel.

## Bloco 2 - Checkout Asaas completo e opcional para pacientes e novos compradores

Objetivo: finalizar pagamentos dentro do sistema, com fluxo seguro para paciente logado e comprador novo.

Atualizacoes minimas do bloco:

1. Revisar o modulo `checkout` atual e listar o que ja esta pronto, pendente e atras de feature flag.
2. Finalizar tela publica de compra de plano com resumo, dados do comprador e redirecionamento seguro.
3. Finalizar tela do paciente logado para pagar mensalidades pendentes.
4. Garantir criacao de pedido antes de criar cobranca remota no Asaas.
5. Usar conta recebedora ativa da clinica como requisito em modo comercial.
6. Validar webhook Asaas com token forte e idempotencia.
7. Baixar mensalidade automaticamente apenas apos evento confirmado.
8. Liberar pacote, assinatura ou acesso digital apenas apos pagamento confirmado.
9. Criar tela administrativa de conciliacao: pedidos pendentes, pagos, expirados e falhos.
10. Adicionar acao de reenviar link de pagamento para paciente.
11. Criar fluxo de cancelamento/expiracao de pedido sem quebrar financeiro.
12. Preparar mensagens de erro amigaveis para Asaas indisponivel, chave ausente ou conta recebedora pendente.
13. Rodar homologacao dry-run e sandbox antes de qualquer pagamento real.
14. Atualizar documentacao `docs/PAGAMENTOS_CHECKOUT_ASAAS.md` com o estado final.

Criterio de pronto: paciente consegue pagar pelo sistema, novo comprador consegue comprar plano, webhooks baixam financeiro e a gestao consegue auditar tudo.

## Bloco 3 - Agenda, remarcacao, presenca e faltas

Objetivo: transformar agenda em fluxo operacional completo, da marcacao ate presenca e reagendamento.

Atualizacoes minimas do bloco:

1. Criar modelo de solicitacao de remarcacao com status pendente, aprovada, recusada e expirada.
2. Permitir que paciente solicite remarcacao por area do paciente ou link seguro.
3. Mostrar solicitacoes pendentes no painel da agenda e no centro operacional.
4. Criar acao da equipe para aprovar remarcacao sem perder historico da aula original.
5. Criar acao da equipe para recusar remarcacao com motivo visivel internamente.
6. Ajustar turmas com varios pacientes para reagendar apenas o aluno solicitado.
7. Criar historico de presenca por aula e por paciente.
8. Registrar status: presente, falta, falta justificada, reagendada, cancelada pela clinica e reposicao.
9. Criar alerta de risco de falta com base em aulas proximas, confirmacao ausente ou historico.
10. Criar lembrete automatico da aula no dia com log de envio.
11. Adicionar tela de frequencia mensal por paciente e por turma.
12. Adicionar filtros persistentes na agenda: profissional, modalidade, status e turma.
13. Melhorar visualizacao mobile da agenda e detalhes da turma.
14. Criar testes para remarcacao individual em turma com mais de um paciente.

Criterio de pronto: equipe consegue operar remarcacao e presenca com seguranca, sem afetar outros pacientes da mesma turma.

## Bloco 4 - Evolucao do paciente, metas, conquistas e check-ins

Objetivo: gerar dados simples de evolucao sem transformar a rotina em prontuario pesado.

Atualizacoes minimas do bloco:

1. Criar avaliacao rapida inicial com objetivos, queixa principal e metas.
2. Criar check-in de dor com opcoes: sem dor, dor leve, dor moderada e dor intensa.
3. Permitir check-in antes ou depois da aula pela equipe.
4. Permitir check-in por link seguro para paciente, se habilitado.
5. Criar modelo de meta do paciente com prazo, status e observacoes.
6. Criar conquistas manuais: meta concluida, frequencia mantida, dor reduzida, retorno e renovacao.
7. Criar conquistas automaticas simples com base em presenca e check-ins.
8. Exibir linha do tempo do paciente com presenca, check-ins, metas e conquistas.
9. Criar comparativo de evolucao entre primeira avaliacao, check-ins e mes atual.
10. Criar resumo clinico leve para a equipe antes do atendimento.
11. Integrar esses dados ao Lume em casa quando o paciente tiver assinatura ativa.
12. Adicionar permissoes para separar dados operacionais de dados clinicos sensiveis.
13. Criar exportacao/relatorio interno com dados agregados, sem exposicao indevida.
14. Adicionar testes de privacidade e acesso por perfil.

Criterio de pronto: a clinica passa a acompanhar frequencia, dor, objetivos e metas de forma mensuravel.

## Bloco 5 - Notificacoes, renovacao, feriados e mudancas de horario

Objetivo: criar um centro de comunicacao util para equipe e paciente, sem depender de mensagens manuais soltas.

Atualizacoes minimas do bloco:

1. Criar central de notificacoes com categorias: agenda, pagamento, renovacao, aniversario, integracao e alerta.
2. Criar log unificado de notificacoes enviadas, falhas, tentativas e canal usado.
3. Criar regra de lembrete da aula no dia.
4. Criar regra de aviso de renovacao do plano com antecedencia configuravel.
5. Criar regra de aviso de falta de credito ou plano vencendo.
6. Criar calendario de feriados, recessos e horarios especiais da clinica.
7. Fazer feriado afetar agenda, disponibilidade e comunicados.
8. Criar aviso em massa para pacientes afetados por mudanca de horario.
9. Criar preferencias de notificacao por paciente quando houver area do paciente.
10. Integrar notificacoes com WhatsApp oficial quando estavel e com WhatsApp Web temporario quando habilitado.
11. Preparar notificacoes PWA para fase posterior, com opt-in explicito.
12. Criar painel de falhas de envio e botao para tentar novamente.
13. Evitar duplicidade de envio com chaves idempotentes por paciente/aula/evento.
14. Criar testes de envio unico e fallback quando o provedor estiver indisponivel.

Criterio de pronto: comunicacao operacional fica rastreavel, previsivel e menos manual.

## Bloco 6 - Programa de indicacao e crescimento

Objetivo: criar mecanismo simples para pacientes indicarem novos alunos, sem complexidade de marketplace.

Atualizacoes minimas do bloco:

1. Criar codigo unico de indicacao por paciente ativo.
2. Criar link publico de indicacao com identificacao segura do indicador.
3. Criar formulario simples para interessado indicado.
4. Registrar origem da indicacao no cadastro do lead/paciente.
5. Criar status: novo, contatado, avaliacao marcada, convertido e perdido.
6. Mostrar indicacoes no painel da recepcao.
7. Criar beneficio manual para indicador, como credito, desconto ou observacao financeira.
8. Criar relatorio de conversao por paciente indicador.
9. Criar protecao contra autoindicacao e duplicidade por telefone/e-mail.
10. Criar mensagem de agradecimento para indicador quando houver conversao.
11. Preparar regra futura de beneficio automatico, mas manter controle manual no inicio.
12. Adicionar filtros e exportacao para campanhas simples.

Criterio de pronto: a clinica consegue rastrear indicacoes e premiar pacientes sem planilha.

## Bloco 7 - Relatorio mensal do paciente e relatorios de gestao

Objetivo: transformar dados de rotina em acompanhamento claro para equipe, gestao e depois paciente.

Atualizacoes minimas do bloco:

1. Criar relatorio mensal por paciente com aulas feitas.
2. Calcular frequencia percentual no periodo.
3. Listar faltas, faltas justificadas e remarcacoes.
4. Mostrar evolucao de dor por check-ins.
5. Mostrar metas abertas, concluidas e atrasadas.
6. Mostrar conquistas do mes.
7. Mostrar renovacao, pagamentos e pendencias relevantes.
8. Criar resumo operacional para equipe: quem precisa de contato e por que.
9. Criar versao imprimivel/PDF para uso interno.
10. Preparar versao compartilhavel com paciente, com linguagem menos tecnica.
11. Adicionar filtros por plano, profissional, turma e periodo.
12. Criar graficos simples e legiveis, sem poluir a tela.
13. Criar testes dos calculos de frequencia e evolucao.
14. Integrar relatorio com dashboard da gestao.

Criterio de pronto: a gestao enxerga frequencia, evolucao e risco de churn de forma mensal.

## Bloco 8 - UX/UI profissional e padronizacao final

Objetivo: manter o mesmo nivel visual entre dashboard, agenda, financeiro, relatorios, Lume em casa, checkout e integracoes.

Atualizacoes minimas do bloco:

1. Revisar telas de financeiro para reduzir ruido e melhorar hierarquia de acoes.
2. Revisar relatorios para leitura executiva, com filtros claros e tabelas responsivas.
3. Revisar Lume em casa para diferenciar conteudo, assinatura, progresso e acesso.
4. Revisar checkout para parecer fluxo de pagamento confiavel e nao tela administrativa.
5. Padronizar botoes primarios, secundarios, destrutivos e compactos.
6. Padronizar badges de status em agenda, financeiro, integracoes e checkout.
7. Padronizar estados vazios com acao recomendada.
8. Padronizar mensagens de erro com problema, causa provavel e proximo passo.
9. Ajustar tabelas operacionais para leitura no celular.
10. Criar acoes por linha consistentes: ver, editar, receber, reagendar, confirmar, cancelar.
11. Criar microcopy para fluxos sensiveis: pagamento, remarcacao, presenca e integracao.
12. Rodar auditoria visual pratica em desktop e mobile antes de deploy.
13. Atualizar `DESIGN.md` quando novos componentes virarem padrao.
14. Evitar novas telas fora do design system.

Criterio de pronto: o sistema inteiro parece um produto unico, profissional e operavel.

## Ordem recomendada

1. Bloco 2: Checkout Asaas, porque impacta receita e compra de planos.
2. Bloco 3: Agenda, remarcacao e presenca, porque impacta a rotina diaria.
3. Bloco 5: Notificacoes, renovacao e feriados, porque depende de agenda/presenca.
4. Bloco 4: Evolucao, metas e check-ins, porque depende da rotina de presenca.
5. Bloco 7: Relatorio mensal, porque depende dos dados acumulados.
6. Bloco 1: PWA pode rodar em paralelo, mas sem cache sensivel.
7. Bloco 6: Indicacao entra depois que checkout e cadastro estiverem mais firmes.
8. Bloco 8: UX/UI deve acontecer ao final de cada bloco e em uma rodada final.

## Guardrails de execucao

- Nao ativar checkout real sem homologacao dry-run e sandbox.
- Nao cachear dados sensiveis no PWA.
- Nao enviar notificacao automatica sem log e chave idempotente.
- Nao permitir remarcacao direta pelo paciente sem aprovacao da equipe.
- Nao alterar presenca sem trilha de auditoria.
- Nao expor dados clinicos em relatorios compartilhaveis sem revisao.
- Nao misturar WhatsApp temporario com caminho SaaS oficial sem feature flag clara.
- Nao criar novos modulos visuais fora do design system.
- Nao subir bloco para VPS sem checklist visual e teste funcional minimo.
- Nao trabalhar em branch suja para grandes mudancas; criar branch limpa por bloco.

## Primeiro pacote recomendado

Bloco 2 iniciado localmente. Itens ja executados neste ciclo:

1. fluxo de compra publica reaproveita pedido pendente recente para evitar cobrancas duplicadas;
2. fluxo de mensalidade do paciente reaproveita pedido pendente existente;
3. servico central `ensure_order_payment_link` protege pedidos pagos, cancelados e expirados;
4. pedidos podem gerar/reabrir link pelo painel administrativo;
5. pedidos pendentes ou falhos podem ser cancelados com nota operacional;
6. pedidos pendentes podem ser marcados como expirados com nota operacional;
7. pedidos pagos nao podem ser cancelados ou expirados pelo painel;
8. lista de pedidos ganhou acoes de conciliacao por linha;
9. tela de status ganhou mensagens especificas para falha, cancelamento e expiracao;
10. testes de checkout foram ampliados para reuso de pedidos e acoes administrativas;
11. suite `checkout` passou com `DB_ENGINE=sqlite`;
12. documentacao de pagamentos Asaas foi atualizada.

Proximas atualizacoes recomendadas para concluir o Bloco 2 em modo homologacao:

1. auditar estado real do checkout Asaas no codigo;
2. revisar feature flags de checkout na VPS e local;
3. finalizar tela publica de compra;
4. finalizar pagamento de mensalidade do paciente;
5. validar conta recebedora ativa;
6. validar webhook idempotente;
7. criar conciliacao administrativa;
8. melhorar mensagens de erro do checkout;
9. rodar homologacao dry-run;
10. preparar homologacao sandbox;
11. documentar comando de ativacao;
12. fazer auditoria visual desktop/mobile.
