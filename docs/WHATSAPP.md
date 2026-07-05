# Integracao WhatsApp

## Recomendacao

Para este projeto, a melhor escolha inicial e a Meta Cloud API com Embedded Signup.

Motivos:

- e a plataforma oficial da Meta;
- evita um intermediario extra no longo prazo;
- combina melhor com um sistema proprio que vai evoluir para notificacoes, webhooks e app;
- os custos seguem diretamente as regras da WhatsApp Business Platform;
- o usuario final conecta a conta Meta por botao, sem copiar token manualmente.

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
5. Uma configuracao de Embedded Signup.
6. O `Meta App ID`, `Meta Configuration ID` e `Meta App Secret`.
7. Templates de mensagem aprovados para avisos enviados fora da janela de 24 horas.

## Variaveis no .env

```text
WHATSAPP_PROVIDER=meta
WHATSAPP_DRY_RUN=True
WHATSAPP_META_API_VERSION=v23.0
WHATSAPP_META_ACCESS_TOKEN=cole-o-token-da-meta
WHATSAPP_META_PHONE_NUMBER_ID=cole-o-phone-number-id
WHATSAPP_EMBEDDED_APP_ID=cole-o-meta-app-id
WHATSAPP_EMBEDDED_CONFIG_ID=cole-o-meta-configuration-id
WHATSAPP_EMBEDDED_APP_SECRET=cole-o-meta-app-secret
WHATSAPP_WEBHOOK_VERIFY_TOKEN=crie-um-token-forte-se-ativar-webhook
WHATSAPP_TIMEOUT=15
LUME_FIELD_ENCRYPTION_KEY=gere-uma-chave-forte-fora-do-git
```

Para a experiencia mais simples do usuario final, preencha `WHATSAPP_EMBEDDED_APP_ID`, `WHATSAPP_EMBEDDED_CONFIG_ID` e `WHATSAPP_EMBEDDED_APP_SECRET` no `.env` da VPS. Assim a tela do sistema mostra o botao `Conectar WhatsApp oficial` e mantem a parte tecnica escondida.

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
- conexao oficial via Meta Embedded Signup;
- mensagens de agendamento, cobranca e aniversario com variaveis prontas;
- envio imediato ou agendado para data e hora especificas;
- fila de proximos disparos com opcao de cancelamento;
- historico recente com status de enviada, simulada, falha ou cancelada.

Pelo terminal:

```powershell
docker compose exec web python manage.py send_test_whatsapp 11999990000 --message "Teste Lume"
```

Na VPS, valide a configuracao sem expor token:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py check_whatsapp_setup
```

Para validar envio ou simulacao:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py check_whatsapp_setup --to 11999990000 --message "Teste Lume"
```

Se `WHATSAPP_DRY_RUN=False`, os comandos bloqueiam envio real por padrao. Para um teste controlado depois de validar numero, token e templates, use explicitamente:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py check_whatsapp_setup --to 11999990000 --message "Teste Lume" --allow-live
```

O comando direto de teste segue a mesma regra:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py send_test_whatsapp 11999990000 --message "Teste Lume" --allow-live
```

Para processar manualmente a fila de mensagens agendadas:

```powershell
docker compose exec web python manage.py process_whatsapp_queue
```

No ambiente Docker, a fila tambem e processada automaticamente pelo servico `worker`.
No app desktop, a fila roda localmente enquanto o aplicativo estiver aberto.

## Importante sobre templates

Mensagens iniciadas pela clinica, como lembrete de vencimento, aniversario, cobranca ou aviso de consulta, normalmente precisam de template aprovado pela Meta quando enviadas fora da janela de atendimento do WhatsApp.

Na aba `Integracoes > Mensagens`, cada modelo interno tem campos para:

- nome do template aprovado na Meta;
- idioma do template, por padrao `pt_BR`;
- variaveis internas usadas na previa.

Enquanto `WHATSAPP_DRY_RUN=True`, o sistema simula envios e usa o texto interno para facilitar testes. Quando `WHATSAPP_DRY_RUN=False`, envios iniciados pela clinica exigem o nome do template aprovado; caso contrario, o sistema bloqueia o disparo com a mensagem `Template nao configurado para producao`.

Templates sugeridos para criar na Meta:

- `lume_lembrete_agendamento`: lembrete ou confirmacao de consulta/sessao.
- `lume_cobranca_pendente`: aviso de mensalidade, pacote ou cobranca avulsa.
- `lume_aniversario_paciente`: mensagem de aniversario para paciente ativo.

Use o idioma `pt_BR` e mantenha a ordem das variaveis igual a previa exibida no sistema. Depois que a Meta aprovar, copie o nome exato do template para a aba `Integracoes > Mensagens`.

Sugestao de homologacao:

1. mantenha `WHATSAPP_DRY_RUN=True`;
2. conecte pela Meta Embedded Signup;
3. configure os nomes dos templates aprovados;
4. envie testes e confira o historico;
5. altere `WHATSAPP_DRY_RUN=False` somente depois de validar numero, templates e permissao da conta.

## Automacoes

O worker agenda e processa automaticamente:

- lembretes de agendamento;
- mensagens de aniversario;
- lembretes de mensalidade a vencer;
- avisos no dia do vencimento, se habilitado;
- avisos de mensalidade vencida;
- avisos de cobranca avulsa vencida.

O sistema evita duplicidade para o mesmo paciente/referencia/data e registra tudo em `WhatsAppMessageLog`.

## URLs publicas

Use `https://sistema.clinicafisiolume.com.br` como base publica para qualquer configuracao futura de callback, webhook ou tela de integracao da Meta. O projeto ainda nao recebe status de mensagem por webhook publico versionado; nao cadastre endpoints inventados no painel da Meta antes de essa etapa ser ativada.
