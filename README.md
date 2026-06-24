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

## Fase 2

- Perfis de acesso: paciente, profissional, administracao e gerencia.
- Vinculo de pacientes a um ou mais profissionais.
- Prontuario individualizado por paciente, visivel apenas ao profissional autor da evolucao.
- Agenda com solicitacao, agendamento, cancelamento, falta e baixa de atendimento.
- Reagendamento e cancelamento sem consumo de creditos do pacote.
- Disponibilidade recorrente por profissional para orientar os horarios possiveis.
- Criacao e reagendamento guiados por horarios livres, sem entrada manual de data/hora pelo usuario.
- Pacotes de atendimentos com contador de aulas/sessoes restantes.
- Despesas e cobrancas avulsas no painel financeiro.
- Categorias editaveis de despesas, com controle de tipo fixo ou variavel.
- Relatorios gerenciais por periodo para pacientes, atendimentos, receitas, despesas e alertas comerciais.
- Lembrete configuravel de mensalidades proximas do vencimento.
- Painel de inadimplentes.
- Auditoria automatica com filtros por periodo, acao, modelo e detalhamento de campos alterados.

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

Usuarios demonstrativos:

```text
Gerencia: admin / Lume@12345
Administracao: recepcao / Recepcao@123
Profissional: helena / Helena@123
Paciente: marina / Marina@123
```

Para encerrar o servidor local iniciado em segundo plano:

```powershell
.\scripts\stop-dev.ps1
```

## Rodando com Docker

Docker e uma boa escolha para este projeto porque padroniza ambiente, facilita backup/deploy e prepara a transicao futura para servidor. Ele nao substitui boas regras de backend, mas reduz problemas de instalacao entre Windows, Linux e macOS.

Quando Docker Desktop estiver instalado:

```bash
docker compose up --build
```

Para parar o container:

```bash
docker compose down
```

## Versionamento

O projeto esta em Git local na branch `main`. Para enviar ao GitHub, crie um repositorio privado e conecte o remoto:

```bash
git remote add origin https://github.com/SEU_USUARIO/lume-gestao.git
git push -u origin main
```

## Proximas fases sugeridas

1. Agenda de atendimentos e presencas.
2. Auditoria detalhada de alteracoes.
3. PostgreSQL e deploy em servidor.
4. Integracao Pix via provedor com webhooks.
5. App do cliente usando a API.
6. Assistente virtual com acesso controlado apenas a dados permitidos.
