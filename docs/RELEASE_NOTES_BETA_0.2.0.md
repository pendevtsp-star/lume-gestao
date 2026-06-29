# Lume Gestao Beta 0.2.0

Release candidata para homologacao de checkout online, Lume Connect e aplicativo mobile.

## Destaques

- Checkout online para compra publica de planos exibidos no site.
- Checkout para paciente logado pagar mensalidades pendentes.
- Provider inicial Asaas com dry-run/sandbox e webhook idempotente.
- Criacao automatica de paciente, usuario de primeiro acesso, mensalidade, pagamento e pacote inicial apos pagamento confirmado.
- Painel interno para acompanhar pedidos e eventos de checkout.
- Feature flags para impedir liberacao acidental em producao.

## Segurança

- O sistema nao armazena dados de cartao.
- Pagamento so efetiva cadastro e financeiro apos webhook validado.
- `CHECKOUT_ENABLED=False` por padrao.
- Em producao estrita, checkout nao liga com `ASAAS_DRY_RUN=True` ou credenciais ausentes.

## Homologacao antes de liberar

- Testar compra publica em sandbox.
- Testar mensalidade pendente de paciente logado.
- Confirmar webhook `/checkout/webhooks/asaas/` com token forte.
- Fazer compra teste de baixo valor antes de ativar no site.
- Manter rollback e backup antes do deploy em producao.
