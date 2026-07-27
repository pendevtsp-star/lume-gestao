# Hardening local, PWA e CI

## Politica de cookies e headers

Os defaults de producao preservam cookies de sessao e CSRF apenas em HTTPS. A
sessao permanece `HttpOnly` por padrao e os dois cookies usam `SameSite=Lax`.
Esses valores continuam configuraveis por ambiente:

- `SESSION_COOKIE_HTTPONLY`
- `SESSION_COOKIE_SAMESITE`
- `CSRF_COOKIE_SAMESITE`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `SECURE_SSL_REDIRECT`

Os headers HSTS, `nosniff`, referrer policy e protecao contra frames continuam
centralizados em `config/settings.py`.

## Limites do service worker

O service worker usa cache-first somente para recursos em `/static/` que tenham
um parametro de versao `v`. A lista de recursos pre-carregados e fechada.

Paginas autenticadas, navegacoes, APIs e rotas clinicas ou financeiras nunca
sao gravadas no cache. Navegacoes usam a rede e recebem apenas uma resposta
offline neutra quando a conexao falha.

Ao alterar um recurso estatico pre-carregado, atualize a versao dos URLs e o
nome de `LUME_CACHE` juntos.

## Validacao local

```powershell
$env:DB_ENGINE='sqlite'
$env:LUME_STRICT_PRODUCTION='False'
.\.venv\Scripts\python.exe manage.py test core.test_hardening
```

O CI executa `manage.py check --deploy --fail-level WARNING` com os controles
HTTPS habilitados. Esse passo valida configuracao e nao modifica o deploy.

## Decisoes sensiveis fora deste ajuste

Nao foram alterados autenticacao, CORS, upload, subprocessos, CSP, COOP,
Permissions-Policy, integracoes externas, banco, volumes ou dados. Mudancas
nesses contratos exigem avaliacao separada de compatibilidade.
