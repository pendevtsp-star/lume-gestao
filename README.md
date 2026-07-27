# Lume Gestao

Sistema de gestao clinica para fisioterapia e pilates. O backend Django e a
fonte da verdade para agenda, pacientes, prontuarios, financeiro, relatorios,
conteudo e automacoes. A producao roda em Docker Compose na VPS e recebe
imagens imutaveis publicadas no GHCR pelo GitHub Actions.

## Estado do produto

- **Ativo:** aplicacao web Django, PostgreSQL, worker de automacoes, WhatsApp
  Web, landing publica, PWA, Lume em Casa, Lume Connect e checkout preparado
  para Asaas.
- **Pausado:** cliente Flutter em `apps/lume_app/` e shell Electron em
  `desktop/`. Eles permanecem versionados, mas nao participam do deploy web.
- **Condicionado a credenciais:** Asaas, Google Agenda e SMTP/Brevo.
- **Legado sem uso operacional:** integracao oficial Meta/WhatsApp. O provedor
  ativo e somente o gateway WhatsApp Web.

O inventario completo esta em [docs/FEATURE_INVENTORY.md](docs/FEATURE_INVENTORY.md).

## Inicio rapido local

### Windows com ambiente Python

```powershell
Copy-Item .env.example .env
.\scripts\dev.ps1
```

Acesse `http://127.0.0.1:8000`. Para encerrar o processo iniciado pelo script:

```powershell
.\scripts\stop-dev.ps1
```

### Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

O ambiente local sobe `db`, `web`, `worker` e `whatsapp-web`. Nunca use
`docker compose down -v` em um ambiente que contenha dados que devam ser
preservados.

Mais comandos e verificacoes: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Arquitetura

```text
Navegador/PWA
    |
    v
Django web/API ---- PostgreSQL
    |                   ^
    v                   |
worker de automacoes ---+
    |
    v
gateway WhatsApp Web
```

- A aplicacao Django concentra autenticacao, autorizacao e regras de negocio.
- O worker usa a mesma imagem da aplicacao e processa automacoes em segundo
  plano.
- O gateway Node mantem a sessao pareada do WhatsApp em volume proprio.
- Midia, backups, arquivos estaticos coletados, sessao WhatsApp e banco sao
  persistentes e nao pertencem ao repositorio Git.

Detalhes: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Qualidade e seguranca

Os workflows ativos estao em `.github/workflows/`:

| Workflow | Responsabilidade |
| --- | --- |
| `ci.yml` | checks Django, drift de migrations, testes com cobertura, Compose e gateway WhatsApp |
| `mobile-flutter.yml` | analise e testes Flutter somente quando `apps/lume_app/**` mudar |
| `security-codeql.yml` | analise semantica Python e JavaScript/TypeScript |
| `security-semgrep.yml` | regras OWASP, Django, JavaScript e segredos |
| `security-trivy.yml` | dependencias, filesystem, Docker e Compose |
| `deploy.yml` | build de imagens, GHCR, migrations, healthchecks, deploy e rollback na VPS |

O deploy parte de `main`. Secrets, `.env`, banco, volumes, midia e backups nao
sao modificados pelos workflows.

## Integracoes

O panorama atual e os gates de ativacao estao em
[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md). Guias detalhados:

- [WhatsApp Web](docs/WHATSAPP.md)
- [Google Agenda](docs/GOOGLE_AGENDA.md)
- [E-mail e Brevo](docs/EMAIL_SMTP.md)
- [Checkout Asaas](docs/PAGAMENTOS_CHECKOUT_ASAAS.md)
- [Lume Connect](docs/LUME_CONNECT.md)

## Producao, backup e recuperacao

- Deploy: [docs/DEPLOY_VPS.md](docs/DEPLOY_VPS.md)
- Atualizacao e rollback: [docs/UPDATE_PRODUCTION.md](docs/UPDATE_PRODUCTION.md)
- Backup e recuperacao: [docs/BACKUP_AND_RECOVERY.md](docs/BACKUP_AND_RECOVERY.md)
- Checklist de seguranca: [docs/SECURITY_PRODUCTION_CHECKLIST.md](docs/SECURITY_PRODUCTION_CHECKLIST.md)

Regra central: nao editar nem versionar `.env`, `data/`, `media/`, backups,
`db.sqlite3`, `staticfiles/` ou volumes Docker. Toda restauracao deve ser
ensaiada e validada antes de substituir dados reais.

## Documentacao

- [Desenvolvimento local](docs/DEVELOPMENT.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Integracoes](docs/INTEGRATIONS.md)
- [Backup e recuperacao](docs/BACKUP_AND_RECOVERY.md)
- [Inventario do produto](docs/FEATURE_INVENTORY.md)
- [Organizacao GitHub](docs/GITHUB_ORGANIZATION.md)
- [Hardening, PWA e CI](docs/HARDENING_PWA_CI.md)
