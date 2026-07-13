# Pagamentos Lume - Checkout Asaas

## Decisao

O provedor inicial de pagamentos sera o Asaas.

Motivos:

- O projeto ja possui o app `checkout` com fluxo de compra publica, pagamento de mensalidade, webhooks e baixa automatica.
- O Asaas cobre Pix, cartao, boleto, cobrancas avulsas e recorrencia.
- O checkout pode operar sem armazenar dados de cartao na VPS.
- O custo de implementacao e homologacao e menor nesta fase.
- iugu e Efi ficam como candidatos futuros se o custo do Pix em planos menores pesar.

## Escopo Do Checkout Central

O app `checkout` e o nucleo para:

- Novo usuario comprar plano publico ofertado no site.
- Paciente logado pagar mensalidade pendente.
- Gestao acompanhar pedidos e webhooks.
- Financeiro receber baixa automatica quando o pagamento for confirmado.
- Registrar eventos de pagamento de forma idempotente.

O modulo `homecare` continua com assinaturas proprias do Lume em casa, mas deve seguir o mesmo padrao de seguranca: ativacao apenas por webhook confirmado ou liberacao manual da gestao.

## Fluxo Comercial Ideal

O fluxo comercial escolhido e preparar o sistema para operar como plataforma, mesmo que a primeira implantacao seja a clinica da sua irma.

- A Lume/plataforma mantem a integracao tecnica central com o Asaas.
- Cada clinica tem uma `CheckoutMerchantAccount`, que representa a conta recebedora daquela instancia.
- O cliente final nao precisa mexer em codigo: ele preenche um cadastro financeiro guiado, envia os dados exigidos pelo provedor e acompanha o status.
- O checkout so deve criar cobrancas remotas com `CHECKOUT_REQUIRE_MERCHANT_ACCOUNT=True` quando a conta recebedora estiver ativa.
- Pedidos de checkout passam a guardar qual conta recebedora foi usada, facilitando auditoria e conciliacao.
- Chaves sensiveis nao devem ser exibidas em tela nem salvas em texto puro. Se a subconta devolver `apiKey`, ela deve ir para armazenamento seguro/criptografado imediatamente.
- O `walletId` da subconta fica salvo como identificador operacional para split/recebimento, sem substituir webhook e idempotencia.

Referencias oficiais consideradas:

- O endpoint de criacao de subconta do Asaas retorna `apiKey` e `walletId`; a `apiKey` e devolvida apenas uma vez e deve ser armazenada com seguranca.
- O split de pagamento exige `walletId` das contas envolvidas, e percentuais sao calculados sobre o valor liquido.
- No split, a propria carteira do emissor nao deve ser indicada; a diferenca liquida nao direcionada fica com o emissor da cobranca.

## Feature Flags

Manter desativado em producao ate homologacao:

```env
CHECKOUT_ENABLED=False
CHECKOUT_PUBLIC_ENABLED=False
CHECKOUT_PATIENT_ENABLED=False
CHECKOUT_WEBHOOK_ENABLED=False
CHECKOUT_PAYMENT_PROVIDER=asaas
CHECKOUT_REQUIRE_MERCHANT_ACCOUNT=False
ASAAS_DRY_RUN=True
ASAAS_BASE_URL=https://api-sandbox.asaas.com/v3
```

Para homologacao local sem custo:

```env
CHECKOUT_ENABLED=True
CHECKOUT_PUBLIC_ENABLED=True
CHECKOUT_PATIENT_ENABLED=True
CHECKOUT_WEBHOOK_ENABLED=True
CHECKOUT_PAYMENT_PROVIDER=asaas
ASAAS_DRY_RUN=True
CHECKOUT_REQUIRE_MERCHANT_ACCOUNT=False
```

Para sandbox real do Asaas:

```env
ASAAS_DRY_RUN=False
ASAAS_BASE_URL=https://api-sandbox.asaas.com/v3
ASAAS_API_KEY=<chave sandbox>
ASAAS_WEBHOOK_TOKEN=<token forte>
CHECKOUT_REQUIRE_MERCHANT_ACCOUNT=True
```

Para producao real, trocar `ASAAS_BASE_URL` para a URL oficial de producao do Asaas e usar chaves reais somente no `.env` da VPS.

## Ordem De Execucao

1. Consolidar `checkout` como nucleo de pagamentos Asaas.
   - Criar painel central `/checkout/`.
   - Mostrar status seguro de provedor, flags, chave configurada, webhook e modo atual.
   - Registrar conta recebedora da clinica e vincular novos pedidos a ela.
   - Manter lista de pedidos e eventos como telas auxiliares.

2. Criar onboarding financeiro da clinica.
   - Formulario guiado para dados cadastrais, contato financeiro, endereco e faturamento/renda mensal.
   - Status: rascunho, em analise, ativa, acao necessaria, rejeitada e desativada.
   - Comando/servico para criar subconta no Asaas sandbox quando as credenciais BaaS estiverem disponiveis.
   - Persistir apenas identificadores seguros; qualquer chave retornada pelo provedor exige armazenamento criptografado.
   - Dados bancarios, senhas, tokens e cartoes nao devem ser informados neste cadastro interno.

3. Homologar fluxo sem custo real.
   - Usar `ASAAS_DRY_RUN=True`.
   - Criar pedido de plano publico.
   - Criar pagamento de mensalidade pendente.
   - Simular webhook confirmado em teste automatizado.
   - Comando seguro: `python manage.py homologate_checkout_dry_run`.
   - Por padrao o comando descarta os dados temporarios ao final.
   - Use `--keep-data` apenas se precisar inspecionar registros de homologacao manualmente.

4. Homologar sandbox real do Asaas.
   - Usar conta/chave sandbox.
   - Ativar `ASAAS_DRY_RUN=False`.
   - Confirmar criacao de cobranca Pix/cartao no ambiente sandbox.
   - Confirmar conta recebedora ativa antes de permitir cobranca remota.
   - Validar webhook com token.
   - Nao fazer compra real com custo nesta etapa.
   - Comando seguro: `python manage.py homologate_checkout_sandbox`.
   - O comando bloqueia qualquer URL que nao seja `https://api-sandbox.asaas.com/v3`.
   - O comando descarta os dados locais por padrao, mas as cobrancas criadas permanecem apenas no sandbox do Asaas.

5. Fortalecer operacao.
   - Adicionar comando de conciliacao de pagamentos pendentes.
   - Melhorar logs de erro do provedor.
   - Criar tela de detalhes do pedido.
   - Auditar alteracoes de status.

6. Preparar producao.
   - Backup de banco e midias.
   - `check --deploy`.
   - Ativar flags por etapas.
   - Teste real pequeno somente com autorizacao.
   - Plano de rollback documentado.

## Seguranca

- Nunca armazenar dados de cartao no banco da Lume.
- Nunca expor `ASAAS_API_KEY` ou `ASAAS_WEBHOOK_TOKEN` no frontend.
- Nunca criar cobranca remota em modo comercial sem conta recebedora ativa.
- Atualizar status financeiro apenas por webhook validado ou acao administrativa auditavel.
- Webhooks devem ser idempotentes.
- Pedidos pagos nao devem ser reprocessados.
- Eventos desconhecidos devem ficar registrados, mas nao devem liberar acesso.
- Produção com `CHECKOUT_ENABLED=True` nao deve rodar com `ASAAS_DRY_RUN=True`.

## Status Atual

- Ponto pausado: integracao Asaas sandbox/subconta aguarda conta CNPJ adequada. Para a clinica atual, o caminho pratico e usar a conta Asaas da propria clinica; para SaaS futuro, sera necessaria uma conta plataforma PJ capaz de criar subcontas/split.
- Item 1 concluido localmente: `checkout` consolidado como nucleo de pagamentos Asaas e com conta recebedora preparada.
- Fluxo comercial iniciado localmente: novos pedidos podem ser vinculados a uma `CheckoutMerchantAccount`.
- Item 2 concluido localmente: tela `/checkout/conta-recebedora/` criada para cadastro financeiro da clinica.
- Item 3 concluido localmente: homologacao dry-run automatizada por teste e comando de gestao.
- Item 4 preparado localmente: comando de sandbox real criado e protegido.
- Conciliacao administrativa reforcada localmente: pedidos agora podem reabrir/gerar link, cancelar ou expirar sem alterar pedidos pagos.
- Reuso de cobrancas pendentes reforcado localmente: compra publica recente e mensalidade pendente do paciente reaproveitam pedido aberto em vez de duplicar cobranca.
- Mensagens de erro do checkout foram padronizadas para orientar paciente e gestao sem expor chaves ou detalhes sensiveis.
- Tentativa local do sandbox real bloqueada com seguranca por ausencia de `ASAAS_API_KEY` sandbox no `.env`.
- Provedor escolhido: Asaas.
- Deploy para VPS deve acontecer apenas junto da atualizacao completa de pagamentos.
- Compra teste com possivel custo real continua adiada para o final da implementacao do modulo.

## Comando De Homologacao Dry-Run

Para rodar localmente sem custo real:

```powershell
$env:CHECKOUT_ENABLED='True'
$env:CHECKOUT_PUBLIC_ENABLED='True'
$env:CHECKOUT_PATIENT_ENABLED='True'
$env:CHECKOUT_WEBHOOK_ENABLED='True'
$env:CHECKOUT_PAYMENT_PROVIDER='asaas'
$env:CHECKOUT_REQUIRE_MERCHANT_ACCOUNT='False'
$env:ASAAS_DRY_RUN='True'
python manage.py homologate_checkout_dry_run
```

O comando valida:

- Criação de pedido de compra publica.
- Criação de pagamento dry-run Asaas.
- Webhook `PAYMENT_CONFIRMED` com Pix.
- Criação automatica de paciente, mensalidade, pagamento quitado e pacote inicial.
- Criação de mensalidade pendente para paciente existente.
- Webhook `PAYMENT_RECEIVED` com cartão.
- Baixa da mensalidade como paga no financeiro.
- Idempotencia dos dois webhooks.

## Comando De Homologacao Sandbox Real

Para rodar com a API sandbox do Asaas, sem custo real:

```powershell
$env:CHECKOUT_ENABLED='True'
$env:CHECKOUT_PUBLIC_ENABLED='True'
$env:CHECKOUT_PATIENT_ENABLED='True'
$env:CHECKOUT_WEBHOOK_ENABLED='True'
$env:CHECKOUT_PAYMENT_PROVIDER='asaas'
$env:CHECKOUT_REQUIRE_MERCHANT_ACCOUNT='True'
$env:ASAAS_DRY_RUN='False'
$env:ASAAS_BASE_URL='https://api-sandbox.asaas.com/v3'
$env:ASAAS_API_KEY='<chave sandbox do Asaas>'
$env:ASAAS_WEBHOOK_TOKEN='<token forte para webhook>'
python manage.py homologate_checkout_sandbox
```

O comando valida:

- Configuracao segura: provider Asaas, flags ativas, `ASAAS_DRY_RUN=False` e URL sandbox oficial.
- Presenca de chave sandbox e token de webhook.
- Conta recebedora ativa quando `CHECKOUT_REQUIRE_MERCHANT_ACCOUNT=True`.
- Criacao real de cliente e cobranca no sandbox do Asaas para compra publica.
- Criacao real de cliente e cobranca no sandbox do Asaas para mensalidade pendente.
- Recebimento de URL de pagamento sandbox.
- Validacao local do webhook com header `asaas-access-token`.
- Baixa financeira por webhook simulado dentro de transacao local.
- Idempotencia do webhook simulado.

Por padrao, o banco local volta ao estado anterior. As cobrancas remotas ficam no ambiente sandbox do Asaas para consulta, mas nao geram custo real.

## Fontes Oficiais

- Asaas API: https://docs.asaas.com/
- Criar subconta Asaas: https://docs.asaas.com/reference/criar-subconta
- Split de pagamentos Asaas: https://docs.asaas.com/docs/split-de-pagamentos
- Assinaturas Asaas: https://docs.asaas.com/docs/assinaturas
- Webhooks Asaas: https://docs.asaas.com/docs/receba-eventos-do-asaas-no-seu-endpoint-de-webhook
- Precos Asaas: https://www.asaas.com/precos-e-taxas
