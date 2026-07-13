# E-mail transacional e marketing com Brevo

O fluxo de recuperacao de senha ja usa envio de e-mail. Em desenvolvimento, o projeto usa o backend de console, que imprime o conteudo nos logs do Docker. Na maquina da clinica, configure SMTP real no arquivo `.env`.

## Regra de uso

- **Transacional:** acesso inicial, recuperacao de senha, documentos fiscais, pagamentos e avisos operacionais. Nao depende de autorizacao de marketing.
- **Marketing:** novidades, campanhas e convites. So pode ser enviado para pacientes com a opcao de autorizacao promocional marcada no cadastro.

O Lume bloqueia o envio de marketing quando o consentimento nao foi registrado. A Brevo tambem deve manter listas e campanhas de marketing separadas das mensagens transacionais.

## Configuracao no painel da Brevo

1. Em **Settings > Senders, Domains & IPs**, crie e verifique os remetentes `nao-responda@clinicafisiolume.com.br` e `contato@clinicafisiolume.com.br`.
2. Em **Domains**, confirme que `clinicafisiolume.com.br` aparece como autenticado, com os registros de codigo Brevo, DKIM e DMARC preservados no DNS.
3. Em **SMTP & API**, gere uma chave SMTP exclusiva para o Lume. Nunca use a senha de login da Brevo no `.env`.
4. Em **Transactional > Webhooks**, crie um webhook HTTPS do Lume para os eventos `delivered`, `soft_bounce`, `hard_bounce`, `blocked`, `spam` e `invalid`.

## Variaveis da VPS

```text
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=Lume Gestao <nao-responda@clinicafisiolume.com.br>
EMAIL_TRANSACTIONAL_FROM_EMAIL=Lume Gestao <nao-responda@clinicafisiolume.com.br>
EMAIL_MARKETING_FROM_EMAIL=Lume Studio <contato@clinicafisiolume.com.br>
EMAIL_REPLY_TO=contato@clinicafisiolume.com.br
EMAIL_BREVO_WEBHOOK_TOKEN=gere-um-token-aleatorio-longo
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=seu-login-brevo
EMAIL_HOST_PASSWORD=sua-chave-smtp-brevo
EMAIL_USE_TLS=True
EMAIL_TIMEOUT=15
```

Use a chave SMTP criada na Brevo. O dominio do remetente precisa estar autenticado; nao use um Gmail como remetente transacional do Lume.

## Webhook de entrega

O Lume ja recebe eventos da Brevo neste endpoint:

```text
https://sistema.clinicafisiolume.com.br/webhooks/brevo/email/?token=COLE_O_MESMO_EMAIL_BREVO_WEBHOOK_TOKEN
```

No painel da Brevo, abra **Transactional > Webhooks > Create webhook**, cole a URL acima e selecione os eventos de entrega. O token deve ser longo e aleatorio, ficar somente no `.env` da VPS e ser o mesmo incluido na URL. Os eventos ficam registrados no admin do Django em **Eventos de entrega de e-mail**.

## Teste

Depois de editar o `.env`, reinicie o sistema:

```powershell
docker compose up -d --build
```

Envie um e-mail de teste:

```powershell
docker compose exec web python manage.py send_test_email destino@exemplo.com
```

Valide a configuracao sem expor senha:

```powershell
docker compose exec web python manage.py check_email_setup
```

Valide conexao e entrega real:

```powershell
docker compose exec web python manage.py check_email_setup --to destino@exemplo.com
```

Se o envio falhar, confira:

- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- bloqueio de SMTP pelo provedor

## Entregabilidade

Para reduzir chance de cair em spam, configure no DNS do dominio:

- SPF autorizando o provedor SMTP.
- DKIM gerado pelo painel do provedor de e-mail.
- DMARC pelo menos em modo monitoramento no inicio.
- Remetente do mesmo dominio do sistema, por exemplo `nao-responda@clinicafisiolume.com.br`.

Esses registros sao configurados no painel DNS/Cloudflare e nao devem carregar senhas ou tokens.

## Recuperacao de senha

A tela publica fica em:

```text
http://127.0.0.1:8000/recuperar-senha/
```

Quando o usuario existe e tem e-mail cadastrado, o sistema envia o link de redefinicao. Quando o login ou e-mail nao existe, a tela retorna `Usuario inexistente.`.
