# Lume Gestao

Sistema local de gestao para uma clinica de fisioterapia e pilates.

## Fase 1

- Login local com permissao administrativa.
- Cadastro de pacientes.
- Cadastro de funcionarios e profissionais.
- Planos, mensalidades e pagamentos manuais.
- Dashboard financeiro inicial.
- API autenticada em `/api/v1/` para evolucao futura do app mobile.
- Testes automatizados para regras sensiveis de cadastro e financeiro.

## Rodando localmente no Windows

```powershell
.\scripts\dev.ps1
```

Depois acesse:

```text
http://127.0.0.1:8000
```

Credenciais de desenvolvimento:

```text
Usuario: admin
Senha: Lume@12345
```

Para encerrar o servidor local iniciado em segundo plano:

```powershell
.\scripts\stop-dev.ps1
```

## Rodando com Docker

Docker e uma boa escolha para este projeto porque padroniza ambiente, facilita backup/deploy e prepara a transicao futura para servidor. Ele nao substitui boas regras de backend, mas reduz problemas de instalacao entre Windows, Linux e macOS.

Quando Docker Desktop estiver instalado:

```bash
cp .env.example .env
docker compose up --build
```

## Proximas fases sugeridas

1. Agenda de atendimentos e presencas.
2. Auditoria detalhada de alteracoes.
3. PostgreSQL e deploy em servidor.
4. Integracao Pix via provedor com webhooks.
5. App do cliente usando a API.
6. Assistente virtual com acesso controlado apenas a dados permitidos.
