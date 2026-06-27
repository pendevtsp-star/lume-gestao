# Lume Gestao Beta 0.1.0

Release candidata para testes beta com usuarios finais selecionados.

## Destaques

- App desktop preparado com Electron para Windows, Linux e macOS.
- Atualizacao automatica preparada via GitHub Releases e `electron-updater`.
- Agenda com sessoes avulsas, recorrentes, compartilhadas, disponibilidade profissional e reagendamento.
- Cadastros de pacientes, profissionais e funcionarios com visualizacao expandida e exclusao/desativacao.
- Modulo financeiro com mensalidades, pagamentos, cobrancas, despesas e relatorios exportaveis.
- PDFs revisados com identidade visual da Lume, melhor distribuicao e assinatura no prontuario.
- Modulo fiscal inicial com geracao/registro de documentos, PDF e caminho de integracao.
- Central de integracoes com WhatsApp, Google Agenda e automacoes preparadas.
- Dados demonstrativos disponiveis via `seed_demo` para testes sem dados reais.

## Correcoes e melhorias recentes

- Ajustes visuais nos principais fluxos de agenda, integracoes e documentos exportaveis.
- Checklist de release beta documentado em `docs/RELEASE_BETA_CHECKLIST.md`.
- Backup local documentado para Docker/PostgreSQL e app desktop.
- Worker de mensagens preparado para processar agendamentos no servidor local e no desktop.

## Limitacoes conhecidas para o beta

- Assinatura de codigo depende dos certificados oficiais configurados nos segredos do GitHub Actions.
- WhatsApp oficial em producao depende da configuracao real da conta Meta/WhatsApp Business.
- Google Agenda em producao depende do OAuth Client configurado no Google Cloud.
- Emissao fiscal oficial depende do provedor escolhido, prefeitura/NFS-e Nacional e credenciais da clinica.
- O beta deve ser usado primeiro com dados demonstrativos ou dados autorizados pela clinica.

## Validacao obrigatoria antes de publicar

- `python manage.py check`
- `python manage.py test`
- GitHub Actions `CI` aprovado na branch `main`.
- Backup e restauracao testados se houver dados reais.
- Instalador desktop validado em maquina limpa antes de enviar a usuarios externos.

## Dados demonstrativos

Para ambiente de teste:

```powershell
python manage.py seed_demo
```

Acesso demonstrativo:

```text
Usuario: admin
Senha: Lume@12345
```

Antes de usar dados reais, manter:

```text
LUME_SEED_DEMO=False
```
