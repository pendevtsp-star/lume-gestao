# Integracao WhatsApp

## Recomendacao

Para este projeto, a melhor escolha inicial e a Meta Cloud API.

Motivos:

- e a plataforma oficial da Meta;
- evita um intermediario extra no longo prazo;
- combina melhor com um sistema proprio que vai evoluir para notificacoes, webhooks e app;
- os custos seguem diretamente as regras da WhatsApp Business Platform.

Quando usar Twilio:

- se a prioridade for testar muito rapido com sandbox;
- se a clinica preferir uma experiencia guiada de onboarding;
- se aceitarmos pagar a camada Twilio alem das tarifas da Meta.

Minha recomendacao pratica: comecar a integracao real pela Meta Cloud API e manter Twilio como plano B para testes ou se o onboarding da Meta travar.

## O que voce precisa criar na Meta

1. Uma conta Meta Business.
2. Um app em Meta for Developers.
3. Um WhatsApp Business Account, tambem chamado WABA.
4. Um numero de telefone aprovado para WhatsApp Business.
5. O `Phone Number ID`.
6. Um token de acesso permanente ou token de sistema com permissao para WhatsApp.
7. Templates de mensagem aprovados para avisos enviados fora da janela de 24 horas.

## Variaveis no .env

```text
WHATSAPP_PROVIDER=meta
WHATSAPP_DRY_RUN=True
WHATSAPP_META_API_VERSION=v23.0
WHATSAPP_META_ACCESS_TOKEN=cole-o-token-da-meta
WHATSAPP_META_PHONE_NUMBER_ID=cole-o-phone-number-id
WHATSAPP_TIMEOUT=15
```

Mantenha `WHATSAPP_DRY_RUN=True` enquanto estiver testando. Assim o sistema simula o envio sem disparar mensagem real.

Quando estiver pronto para enviar de verdade:

```text
WHATSAPP_DRY_RUN=False
```

## Teste

Pela tela:

```text
http://127.0.0.1:8000/integracoes/
```

Em producao:

```text
https://sistema.clinicafisiolume.com.br/integracoes/
```

Recursos principais da tela:

- configuracao do numero principal da clinica;
- mensagens de agendamento, cobranca e aniversario com variaveis prontas;
- envio imediato ou agendado para data e hora especificas;
- fila de proximos disparos com opcao de cancelamento;
- historico recente com status de enviada, simulada, falha ou cancelada.

Pelo terminal:

```powershell
docker compose exec web python manage.py send_test_whatsapp 11999990000 --message "Teste Lume"
```

Para processar manualmente a fila de mensagens agendadas:

```powershell
docker compose exec web python manage.py process_whatsapp_queue
```

No ambiente Docker, a fila tambem e processada automaticamente pelo servico `worker`.
No app desktop, a fila roda localmente enquanto o aplicativo estiver aberto.

## Importante sobre templates

Mensagens iniciadas pela clinica, como lembrete de vencimento ou aviso de consulta, normalmente precisam de template aprovado pela Meta quando enviadas fora da janela de atendimento do WhatsApp. O modulo atual prepara texto simples para teste; a proxima etapa de producao deve adicionar envio por templates.

## URLs publicas

Use `https://sistema.clinicafisiolume.com.br` como base publica para qualquer configuracao futura de callback, webhook ou tela de integracao da Meta. O projeto atual nao possui endpoint publico de webhook do WhatsApp versionado; nao cadastre endpoints inventados no painel da Meta.
