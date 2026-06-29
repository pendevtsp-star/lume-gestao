# Checkout online

Modulo para compra de planos pelo site e pagamento de mensalidades pelo paciente logado.

## Rotas

- Compra publica de plano: `/checkout/planos/<id>/`
- Status do pedido: `/checkout/pedido/<referencia>/`
- Mensalidades do paciente: `/checkout/minhas-mensalidades/`
- Webhook Asaas: `/checkout/webhooks/asaas/`
- Gestao interna: `/checkout/pedidos/` e `/checkout/eventos/`

## Flags de seguranca

Mantenha tudo desligado ate homologar em sandbox:

```text
CHECKOUT_ENABLED=False
CHECKOUT_PUBLIC_ENABLED=False
CHECKOUT_PATIENT_ENABLED=False
CHECKOUT_WEBHOOK_ENABLED=False
CHECKOUT_PAYMENT_PROVIDER=asaas
ASAAS_DRY_RUN=True
```

Em producao com `LUME_STRICT_PRODUCTION=True`, o sistema bloqueia `CHECKOUT_ENABLED=True`
se `ASAAS_DRY_RUN=True` ou se `ASAAS_API_KEY`/`ASAAS_WEBHOOK_TOKEN` estiverem ausentes.

## Fluxo seguro

1. O site cria apenas um `CheckoutOrder` pendente.
2. Paciente, mensalidade, pagamento e pacote so sao criados/alterados depois do webhook confirmado.
3. O webhook valida `ASAAS_WEBHOOK_TOKEN`.
4. Eventos repetidos sao tratados por `event_id`, evitando duplicidade.
5. O sistema nao armazena dados de cartao.

## Compra de plano

Ao confirmar pagamento:

1. Localiza paciente por CPF, e-mail ou telefone, ou cria um novo paciente.
2. Cria usuario de primeiro acesso e envia credenciais pelo onboarding existente.
3. Marca aceite LGPD no perfil criado.
4. Cria mensalidade ativa.
5. Registra o pagamento do mes como pago.
6. Cria um pacote inicial de sessoes com `sessions_per_week * 4`.

## Pagamento de mensalidade

Paciente logado pode pagar mensalidades pendentes. Ao webhook confirmado, o `Payment`
vinculado muda para `Pago` e recebe metodo conforme payload do provedor.

## Homologacao recomendada

1. Ativar em ambiente local ou VPS de teste com `ASAAS_DRY_RUN=True`.
2. Testar criacao de pedido publico sem webhook real.
3. Testar webhook via payload de sandbox.
4. Conferir criacao de paciente, usuario, mensalidade, pagamento e pacote.
5. So depois trocar Asaas para sandbox real ou producao.
6. Fazer compra teste de baixo valor antes de liberar para pacientes reais.
