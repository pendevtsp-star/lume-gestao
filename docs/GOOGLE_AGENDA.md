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

Em producao, use a URL publica oficial:

```text
https://sistema.clinicafisiolume.com.br/integracoes/google/callback/
```

Nao use IP fixo nas credenciais de producao. O dominio `sistema.clinicafisiolume.com.br` sera apontado para a VPS pelo DNS da Cloudflare.

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

Em producao na VPS, prefira manter `GOOGLE_CALENDAR_CLIENT_ID` e `GOOGLE_CALENDAR_CLIENT_SECRET` no arquivo `.env` do servidor. A tela de integracoes mostra apenas o botao `Conectar com Google`; os campos tecnicos ficam recolhidos em `Configuracao tecnica do Google`.

## Uso no sistema

Entre como gerencia e acesse:

```text
http://127.0.0.1:8000/integracoes/
```

Em producao:

```text
https://sistema.clinicafisiolume.com.br/integracoes/
```

Clique em `Conectar com Google`, escolha a conta Google da clinica, autorize o acesso e depois use `Sincronizar agora`.

Pelo terminal da VPS, valide sem expor segredos:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py check_google_calendar_setup
```

Depois de conectar a conta pela tela, voce tambem pode testar uma sincronizacao:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py check_google_calendar_setup --sync
```

Com a integracao conectada e a opcao de sincronizacao habilitada:

- novos agendamentos podem ser enviados automaticamente para o Google Calendar;
- alteracoes de horario passam a refletir no evento vinculado;
- exclusoes removem o evento remoto correspondente.

Se quiser usar a sincronizacao continua, mantenha a integracao:

- `Ativada`
- com `Sincronizar automaticamente` habilitado
- com credenciais OAuth validas no `.env`

## Observacao

A sincronizacao direta depende do OAuth. Se a clinica ainda nao quiser criar credenciais Google, a exportacao `.ics` continua disponivel em `Agenda > Google Agenda .ics`.
