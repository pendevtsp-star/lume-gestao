# Arquitetura do Lume Gestao

## Visao geral

O Lume e um monolito modular Django. HTML, PWA e API usam o mesmo backend e as
mesmas regras de autorizacao. PostgreSQL e a fonte persistente de producao.

| Camada | Componentes | Responsabilidade |
| --- | --- | --- |
| Interface | `templates/`, `static/`, PWA | operacao web, mobile web e landing publica |
| Aplicacao | apps Django | autenticacao, agenda, pacientes, financeiro, conteudo e relatorios |
| Processamento | `worker` | fila de mensagens e automacoes recorrentes |
| Integracao | `whatsapp-web-gateway/` | sessao WhatsApp Web e envio pelo gateway local |
| Dados | PostgreSQL, `media/`, volumes | dados transacionais, arquivos e sessoes persistentes |

## Modulos Django

- `accounts`: identidade, perfis e autorizacao.
- `patients`: cadastro e informacoes clinicas do paciente.
- `scheduling`: agenda, turmas, vagas, recorrencia, presenca e reagendamento.
- `billing`, `checkout` e `fiscal`: cobrancas, pagamentos, checkout e fiscal.
- `reports`: consultas e exportacoes gerenciais.
- `homecare`: Lume em Casa e sua jornada operacional.
- `lume_connect`: conteudo e rede interna autenticada.
- `website`: landing publica e conteudo configuravel.
- `core`, `team` e `mobile`: funcoes compartilhadas, equipe e API cliente.

## Containers

- `db`: PostgreSQL 16 com volume `postgres_data`.
- `web`: imagem principal Django, healthcheck HTTP e volumes de midia,
  estaticos coletados e backups.
- `worker`: mesma imagem da aplicacao, comando dedicado e acesso aos volumes
  necessarios para automacoes.
- `whatsapp-web`: imagem Node separada e sessao persistida em
  `data/whatsapp-web`.

## Principios

1. O backend e a fonte da verdade; validacoes sensiveis nao ficam apenas no
   navegador.
2. Views devem adaptar HTTP; consultas reutilizaveis ficam em selectors e
   mutacoes transacionais em services.
3. URLs publicas e contratos de API mudam apenas com compatibilidade explicita.
4. Migrations sao incrementais e nunca substituem backup.
5. Dados reais, secrets e volumes nao pertencem ao Git nem as imagens Docker.
6. O deploy usa imagens por SHA e so promove a tag `production` depois de
   migrations e healthchecks aprovados.

## Clientes pausados

`apps/lume_app/` e o cliente Flutter planejado para Android/iOS. `desktop/` e
um shell Electron historico. Ambos permanecem no repositorio para retomada,
mas nao alteram o runtime ou deploy da aplicacao web.

Para a linha de base tecnica detalhada da refatoracao local, consulte
`docs/architecture/baseline-2026-07-21.md`.
