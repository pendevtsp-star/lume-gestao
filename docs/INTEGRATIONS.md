# Integracoes

Este documento resume o estado operacional. Credenciais reais existem somente
nos ambientes autorizados e nunca devem ser copiadas para o repositorio.

| Integracao | Estado | Runtime | Gate para uso real |
| --- | --- | --- | --- |
| WhatsApp Web | ativa | `worker` + `whatsapp-web` | sessao QR conectada, token interno e healthcheck saudavel |
| Meta WhatsApp oficial | legado/inativa | nenhum | nao reativar sem projeto e revisao separados |
| SMTP/Brevo | condicionada | Django/worker | dominio, remetente e credenciais SMTP/API validados |
| Google Agenda | preparada, nao operacional | Django | OAuth e redirect URI configurados e homologados |
| Asaas | preparada | Django + webhook | credenciais sandbox, webhook idempotente e homologacao antes de producao |
| Lume Connect | ativa/interna | Django + media | usuario autenticado e limites de upload configurados |
| IA para legendas | futura/desativada | Django | provedor, modelo, chave e politica de dados aprovados |

## WhatsApp Web

O unico provedor operacional e `WHATSAPP_PROVIDER=web_gateway`. O QR conecta a
conta da clinica ao gateway, e o worker processa a fila de mensagens. Manter
`WHATSAPP_DRY_RUN=True` ate concluir validacao controlada em novo ambiente.

Detalhes: `docs/WHATSAPP.md`.

## E-mail e Brevo

Em desenvolvimento, o backend de console evita envios externos. Em producao,
o remetente autenticado, credenciais e webhook de eventos devem ser validados
antes de liberar automacoes.

Detalhes: `docs/EMAIL_SMTP.md`.

## Google Agenda

A integracao permanece preparada, mas nao faz parte da rotina operacional. A
alternativa `.ics` pode ser usada sem conceder OAuth. Nao habilitar sincronismo
real sem credenciais, consentimento e teste de duplicidade.

Detalhes: `docs/GOOGLE_AGENDA.md`.

## Asaas

O checkout deve permanecer em dry-run ate que sandbox, assinatura do webhook,
idempotencia e reconciliacao tenham sido validados. O sistema nao armazena
dados de cartao.

Detalhes: `docs/PAGAMENTOS_CHECKOUT_ASAAS.md` e `docs/CHECKOUT_ONLINE.md`.

## Diagnostico sem expor secrets

```bash
docker compose exec web python manage.py check_email_setup
docker compose exec web python manage.py check_google_calendar_setup
docker compose exec web python manage.py check_whatsapp_setup
docker compose exec web python manage.py check_checkout_readiness
```

Os resultados podem indicar presenca ou ausencia de configuracao, mas nao
devem imprimir tokens, senhas ou chaves completas.
