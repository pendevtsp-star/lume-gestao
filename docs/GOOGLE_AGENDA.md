# Integracao Google Agenda

O Lume Gestao ja possui exportacao `.ics`. Esta etapa adiciona a base OAuth para sincronizar diretamente com Google Calendar.

## O que precisa ser criado no Google

1. Acesse Google Cloud Console.
2. Crie ou selecione um projeto.
3. Ative a Google Calendar API.
4. Configure a tela de consentimento OAuth.
5. Crie uma credencial do tipo `OAuth Client ID` para aplicativo web.
6. Adicione a URL de callback:

```text
http://127.0.0.1:8000/integracoes/google/callback/
```

Na maquina da clinica, use tambem a URL com IP local:

```text
http://IP_DA_MAQUINA_DA_CLINICA:8000/integracoes/google/callback/
```

## Variaveis no .env

```text
GOOGLE_CALENDAR_CLIENT_ID=cole-o-client-id-google
GOOGLE_CALENDAR_CLIENT_SECRET=cole-o-client-secret-google
GOOGLE_CALENDAR_TIMEOUT=15
```

Depois reinicie:

```powershell
docker compose up -d --build
```

## Uso no sistema

Entre como gerencia e acesse:

```text
http://127.0.0.1:8000/integracoes/
```

Clique em `Conectar`, autorize a conta Google e depois use `Sincronizar agenda`.

## Observacao

A sincronizacao direta depende do OAuth. Se a clinica ainda nao quiser criar credenciais Google, a exportacao `.ics` continua disponivel em `Agenda > Google Agenda .ics`.
