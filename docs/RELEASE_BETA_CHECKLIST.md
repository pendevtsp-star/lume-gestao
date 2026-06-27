# Checklist de release beta

Use este checklist antes de liberar uma versao beta do Lume Gestao para usuarios finais. A meta e garantir que backup, atualizacao, instalador desktop, assinatura e dados de teste estejam prontos antes da primeira instalacao externa.

## 1. Corte da versao

- [ ] Confirmar que a branch `main` esta atualizada e sem alteracoes locais pendentes.
- [ ] Revisar o numero da versao em `desktop/package.json`.
- [ ] Definir nome da release, por exemplo `Beta 0.1.0`.
- [ ] Criar notas resumidas da versao com novidades, correcoes conhecidas e limitacoes.
- [ ] Rodar CI local minimo antes do corte:

```powershell
python manage.py check
python manage.py test
```

- [ ] Confirmar que o GitHub Actions `CI` passou na branch `main`.

## 2. Backup e restauracao

- [ ] Fazer backup antes de qualquer atualizacao em maquina com dados reais.
- [ ] Guardar banco, arquivos enviados, `.env` e configuracoes locais fora da pasta instalada do app.
- [ ] Validar restauracao em ambiente separado antes de considerar o backup confiavel.
- [ ] Manter ao menos uma copia externa criptografada.
- [ ] Registrar data, responsavel e local seguro do backup.

### Servidor local com Docker/PostgreSQL

```powershell
.\scripts\clinic-backup.ps1
```

O script gera arquivos em `backups/`. Antes do beta, validar que existem:

- [ ] backup SQL do banco;
- [ ] backup compactado de `media/`, quando houver arquivos enviados;
- [ ] copia segura do `.env`.

Restauracao de validacao sugerida:

```powershell
Get-Content -Raw backups\arquivo_do_backup.sql | docker compose exec -T db psql -U lume -d lume
```

### App desktop local

Quando `LUME_DESKTOP=True`, os dados locais ficam em:

- Windows: `%APPDATA%/Lume Gestao/backend-data`
- macOS: `~/Library/Application Support/Lume Gestao/backend-data`
- Linux: `~/.config/Lume Gestao/backend-data`

Antes de atualizar:

- [ ] Copiar `db.sqlite3`.
- [ ] Copiar a pasta `media/`.
- [ ] Copiar eventuais arquivos de configuracao local.
- [ ] Abrir a copia em uma instalacao limpa e confirmar login, pacientes, agenda e financeiro.

## 3. Atualizacao automatica

- [ ] Confirmar que `electron-updater` esta ativo no desktop.
- [ ] Confirmar que `desktop/package.json` publica releases em `pendevtsp-star/lume-gestao`.
- [ ] Gerar release por tag no formato `desktop-vX.Y.Z`.
- [ ] Confirmar que `.github/workflows/desktop-release.yml` gerou Windows, Linux e macOS.
- [ ] Testar atualizacao de uma versao anterior para a nova em maquina limpa.
- [ ] Confirmar que o app avisa quando a atualizacao esta pronta.
- [ ] Confirmar que migracoes do backend rodam sem perda de dados.
- [ ] Fazer backup automatico/manual antes da primeira abertura apos update.
- [ ] Manter instalador anterior disponivel para rollback.

Fluxo recomendado:

```powershell
git tag desktop-v0.1.0
git push origin desktop-v0.1.0
```

Depois do workflow:

- [ ] Baixar instaladores publicados na release.
- [ ] Instalar em maquina sem ambiente de desenvolvimento.
- [ ] Validar abertura, login, fechamento e reabertura.
- [ ] Validar que os dados locais permanecem apos reinstalar por cima.

## 4. Assinatura do app desktop

### Windows

- [ ] Obter certificado de assinatura de codigo para distribuicao publica.
- [ ] Gerar ou receber arquivo `.pfx`.
- [ ] Cadastrar segredos no GitHub Actions:

```text
WIN_CSC_LINK
WIN_CSC_KEY_PASSWORD
```

- [ ] Validar timestamp de assinatura.
- [ ] Instalar o `.exe` em Windows limpo e verificar alerta do SmartScreen.
- [ ] Confirmar que o instalador e o executavel aparecem como assinados.

### macOS

- [ ] Ter conta Apple Developer ativa.
- [ ] Configurar certificado Developer ID Application.
- [ ] Cadastrar segredos no GitHub Actions:

```text
CSC_LINK
CSC_KEY_PASSWORD
APPLE_ID
APPLE_APP_SPECIFIC_PASSWORD
APPLE_TEAM_ID
```

- [ ] Validar notarizacao.
- [ ] Instalar o `.dmg` em macOS limpo.
- [ ] Confirmar que o Gatekeeper permite abertura sem instrucoes tecnicas ao usuario.

### Linux

- [ ] Gerar `AppImage` e `.deb`.
- [ ] Publicar checksum SHA256 dos artefatos.
- [ ] Opcional: assinar checksums com GPG.
- [ ] Testar instalacao em Ubuntu/Debian limpo.

## 5. Dados de teste beta

- [ ] Usar `LUME_SEED_DEMO=True` apenas para ambiente de teste/demonstracao.
- [ ] Usar `LUME_SEED_DEMO=False` antes de cadastrar dados reais da clinica.
- [ ] Confirmar que a base beta nao contem CPF, telefone, e-mail ou prontuario real sem consentimento.
- [ ] Criar uma clinica demonstrativa com:
  - [ ] usuario admin;
  - [ ] profissional;
  - [ ] funcionario;
  - [ ] pacientes ativos e inativos;
  - [ ] agenda individual, recorrente e grupo;
  - [ ] mensalidades, pagamentos, cobrancas e despesas;
  - [ ] templates de WhatsApp;
  - [ ] documentos fiscais de teste;
  - [ ] prontuario demonstrativo.
- [ ] Validar que dados demonstrativos podem ser removidos antes do uso real.
- [ ] Separar claramente ambiente `teste` de ambiente `real`.

Comando de dados demonstrativos:

```powershell
python manage.py seed_demo
```

Acesso demonstrativo:

```text
Usuario: admin
Senha: Lume@12345
```

## 6. Validacao funcional do beta

- [ ] Login admin.
- [ ] Cadastro, busca, edicao, visualizacao e exclusao/desativacao de pacientes.
- [ ] Cadastro, busca, edicao e exclusao/desativacao de profissionais e funcionarios.
- [ ] Agenda semanal, disponibilidade, recorrencia, grupo, reagendamento e cancelamento.
- [ ] Financeiro: mensalidade, pagamento, cobranca, despesa e relatorios.
- [ ] Fiscal: criacao de documento, PDF, status e orientacao de integracao.
- [ ] WhatsApp: numero da clinica, templates, agendamento e envio em modo teste.
- [ ] Google Agenda: tela de conexao, status, sincronizacao manual e desconexao.
- [ ] PDFs: logo no topo, espacamento, assinatura quando aplicavel e leitura em A4.
- [ ] Backup antes e depois da atualizacao.
- [ ] Worker de mensagens ativo no Docker e no desktop.

## 7. Seguranca minima antes do beta

- [ ] `DEBUG=False` em qualquer ambiente externo.
- [ ] `SECRET_KEY` forte e unica por instalacao.
- [ ] `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` restritos.
- [ ] Credenciais Google, WhatsApp, fiscal, SMTP e banco fora do Git.
- [ ] Permissoes verificadas no backend, nao apenas no frontend.
- [ ] Logs sem tokens, senhas, CPF completo ou dados sensiveis desnecessarios.
- [ ] Backup criptografado quando sair da maquina da clinica.
- [ ] Revisar `docs/SEGURANCA_CHECKLIST.md`.
- [ ] Rodar:

```powershell
python manage.py check --deploy
```

## 8. Go/no-go

Liberar beta apenas se todos os itens abaixo estiverem marcados:

- [ ] Backup criado e restaurado com sucesso.
- [ ] Instaladores desktop gerados para os sistemas alvo.
- [ ] Assinatura configurada ou risco de app sem assinatura comunicado ao usuario beta.
- [ ] Atualizacao automatica testada ou plano manual de atualizacao documentado.
- [ ] Base de teste sem dados reais indevidos.
- [ ] Fluxos principais aprovados em navegador e desktop.
- [ ] Nenhum bug critico aberto em login, agenda, financeiro, prontuario, fiscal ou backup.
- [ ] Rollback preparado com instalador anterior e backup anterior.

## 9. Registro da release

| Item | Responsavel | Data | Evidencia |
| --- | --- | --- | --- |
| CI aprovado |  |  |  |
| Backup criado |  |  |  |
| Restore testado |  |  |  |
| Build Windows |  |  |  |
| Build Linux |  |  |  |
| Build macOS |  |  |  |
| Assinatura Windows |  |  |  |
| Assinatura macOS |  |  |  |
| Atualizacao testada |  |  |  |
| Dados demo revisados |  |  |  |
| Smoke test final |  |  |  |

## 10. Pos-release beta

- [ ] Monitorar relatos dos usuarios nas primeiras 48 horas.
- [ ] Conferir logs de erro e falhas de worker.
- [ ] Conferir se backups continuam sendo criados.
- [ ] Confirmar que nenhum usuario ficou preso em versao antiga.
- [ ] Registrar bugs por prioridade.
- [ ] Planejar patch rapido se houver bug critico.
