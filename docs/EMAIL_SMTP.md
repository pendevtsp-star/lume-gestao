# Configuracao de e-mail SMTP

O fluxo de recuperacao de senha ja usa envio de e-mail. Em desenvolvimento, o projeto usa o backend de console, que imprime o conteudo nos logs do Docker. Na maquina da clinica, configure SMTP real no arquivo `.env`.

## Variaveis

```text
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=Lume Gestao <nao-responda@clinicafisiolume.com.br>
EMAIL_HOST=smtp.clinicafisiolume.com.br
EMAIL_PORT=587
EMAIL_HOST_USER=nao-responda@clinicafisiolume.com.br
EMAIL_HOST_PASSWORD=troque-esta-senha-do-email
EMAIL_USE_TLS=True
EMAIL_TIMEOUT=15
```

Para Gmail ou Google Workspace, use uma senha de app. Para provedores como Hostinger, Locaweb, Registro.br ou outros, use os dados SMTP fornecidos pelo painel do e-mail.

## Teste

Depois de editar o `.env`, reinicie o sistema:

```powershell
docker compose up -d --build
```

Envie um e-mail de teste:

```powershell
docker compose exec web python manage.py send_test_email destino@exemplo.com
```

Se o envio falhar, confira:

- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- bloqueio de SMTP pelo provedor

## Recuperacao de senha

A tela publica fica em:

```text
http://127.0.0.1:8000/recuperar-senha/
```

Quando o usuario existe e tem e-mail cadastrado, o sistema envia o link de redefinicao. Quando o login ou e-mail nao existe, a tela retorna `Usuario inexistente.`.
