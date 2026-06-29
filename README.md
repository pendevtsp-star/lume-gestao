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

## Checkout online

- Compra publica de planos exibidos no site e pagamento de mensalidades pelo paciente logado.
- Provider inicial: Asaas, sempre atras de feature flags e webhook idempotente.
- O sistema nao armazena dados de cartao; dados clinicos/cadastrais so sao efetivados apos confirmacao do pagamento.

Detalhes de homologacao:

```text
docs/CHECKOUT_ONLINE.md
```

## Lume Connect

- Rede social interna em `/lume-connect/`, disponivel para usuarios autenticados e ativos.
- Posts com texto e imagem, curtidas, comentarios, busca, filtros por avisos/fotos e pagina simples de perfil.
- Moderacao por administracao, gerencia ou superusuario; exclusoes removem itens do feed sem apagar os registros fisicos.
- Uploads usam `MEDIA_ROOT`/`MEDIA_URL` existentes e aceitam JPG, JPEG, PNG e WEBP. O limite padrao e `LUME_CONNECT_MAX_IMAGE_MB=8`.
- Videos curtos ficam em `MEDIA_ROOT/lume_connect/videos/`, aceitam MP4/MOV/WEBM, usam autoplay controlado no feed e respeitam `LUME_CONNECT_MAX_SHORT_VIDEO_SECONDS=60` e `LUME_CONNECT_MAX_VIDEO_MB=80`.
- A validacao de duracao usa `ffprobe`; o upload e otimizado para MP4/H.264 com `ffmpeg` e gera capa automaticamente quando o usuario nao envia uma capa.
- Submodulo "Compartilhar nas redes" para posts com imagem do proprio autor: gerar legenda, editar, copiar, baixar imagem e usar compartilhamento nativo do celular.
- Instagram nesta versao e manual: baixe a imagem, copie a legenda e publique pelo app. Publicacao direta via API Meta/Instagram fica para uma etapa futura com OAuth, conta profissional e permissoes oficiais.
- A legenda funciona sem IA externa. Para preparar uma integracao futura, configure `AI_CAPTION_ENABLED`, `AI_PROVIDER`, `AI_API_KEY` e `AI_CAPTION_MODEL`; chaves reais devem ficar apenas no `.env`.

Para ativar em ambientes existentes, aplique apenas migrations incrementais:

```bash
python manage.py migrate
```

Com Docker, use o container atual sem apagar volumes:

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
```

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
Tambem sobe um servico `worker` para processar mensagens WhatsApp agendadas em segundo plano.

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
ENVIRONMENT=production
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.0.50
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://192.168.0.50:8000
DEBUG=False
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
Quando ha mensagens WhatsApp agendadas, o desktop processa a fila localmente enquanto o app estiver aberto.

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

Guias curtos por sistema operacional:

```text
docs/INSTALACAO_RESUMIDA.md
docs/INSTALACAO_WINDOWS.md
docs/INSTALACAO_MACOS.md
docs/INSTALACAO_LINUX.md
```

## Instalacao de teste na clinica

Para instalar em uma maquina da clinica na rede local, siga o roteiro em:

```text
docs/INSTALACAO_CLINICA.md
```

## E-mail e recuperacao de senha

O fluxo de recuperacao de senha fica em `/recuperar-senha/`. Em desenvolvimento, os e-mails aparecem no console do Docker. Para envio real por SMTP, siga:

```text
docs/EMAIL_SMTP.md
```

Para testar a configuracao SMTP:

```bash
docker compose exec web python manage.py send_test_email destino@exemplo.com
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

O roadmap atualizado dos itens 3 a 7 esta salvo em:

```text
docs/PROXIMOS_PASSOS.md
```

Documentacao das integracoes:

```text
docs/LUME_CONNECT.md
docs/GOOGLE_AGENDA.md
docs/WHATSAPP.md
```

Deploy em VPS Linux com Docker Compose, PostgreSQL, Nginx, HTTPS e Cloudflare:

```text
docs/DEPLOY_VPS.md
docs/UPDATE_PRODUCTION.md
docs/SECURITY_PRODUCTION_CHECKLIST.md
```
