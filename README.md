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
- Exportacao de relatorios e prontuarios em PDF e Excel.
- Pacotes de atendimentos com contador de aulas/sessoes restantes.
- Despesas e cobrancas avulsas no painel financeiro.
- Categorias editaveis de despesas, com controle de tipo fixo ou variavel.
- Relatorios gerenciais por periodo para pacientes, atendimentos, receitas, despesas e alertas comerciais.
- Lembrete configuravel de mensalidades proximas do vencimento.
- Painel de inadimplentes.
- Auditoria automatica com filtros por periodo, acao, modelo e detalhamento de campos alterados.
- API com filtragem por perfil e permissao por objeto para dados clinicos, agenda e financeiro.

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

O ambiente Docker usa PostgreSQL local. Nao e necessario criar conta externa no PostgreSQL: o proprio `docker compose` cria um container de banco com usuario, senha e base configurados no arquivo `.env`.

Quando Docker Desktop estiver instalado:

```bash
docker compose up --build
```

Para parar o container:

```bash
docker compose down
```

Os dados do PostgreSQL ficam no volume Docker `postgres_data`, entao continuam salvos apos `docker compose down`. Para reiniciar do zero durante desenvolvimento, use apenas quando tiver certeza de que pode apagar os dados:

```bash
docker compose down -v
```

## Rodando em outra maquina Linux

Em uma maquina Linux com Docker e Docker Compose instalados:

```bash
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd lume-gestao
cp .env.example .env
```

Edite o `.env` e inclua o IP da maquina Linux em `ALLOWED_HOSTS`, por exemplo:

```text
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.0.50
DEBUG=True
DB_ENGINE=postgres
POSTGRES_DB=lume
POSTGRES_USER=lume
POSTGRES_PASSWORD=troque-esta-senha
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

Depois suba o sistema:

```bash
docker compose up --build
```

Na propria maquina Linux, acesse:

```text
http://127.0.0.1:8000
```

Em outro computador da mesma rede, acesse pelo IP da maquina Linux:

```text
http://192.168.0.50:8000
```

Se o navegador de outra maquina nao abrir, verifique firewall/liberacao da porta `8000` na maquina Linux. Para testar com dados demonstrativos, basta iniciar o container.

Roteiro completo, incluindo copia via `.zip` e build desktop Linux:

```text
docs/INSTALACAO_LINUX.md
```

## App desktop

O projeto agora possui um shell desktop em Electron em `desktop/`. Ele abre a interface Django existente e inicia um backend local na propria maquina, usando SQLite e salvando dados na pasta de dados do usuario do app.

Durante desenvolvimento:

```powershell
cd desktop
npm install
npm start
```

Para gerar instalador Windows:

```powershell
.\scripts\build-desktop.ps1
```

Mais detalhes, incluindo macOS, Linux e caminho futuro para VPS, estao em `docs/APP_DESKTOP.md`.

## Instalacao de teste na clinica

Para instalar em uma maquina da clinica na rede local, siga o roteiro em:

```text
docs/INSTALACAO_CLINICA.md
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
