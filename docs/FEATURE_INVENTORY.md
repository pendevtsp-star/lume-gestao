# Inventario do produto

Inventario de alto nivel da versao local atual. O status descreve entrega e
runtime, nao substitui homologacao com credenciais externas.

## Ativo

- autenticacao, perfis e permissoes;
- dashboard operacional;
- pacientes, prontuario, metas e evolucao;
- agenda, disponibilidade, turmas, recorrencia, vagas e reagendamento;
- presenca, faltas, justificativas e creditos;
- planos, mensalidades, pagamentos, despesas e cobrancas avulsas;
- relatorios e exportacoes;
- landing publica configuravel;
- PWA web sem cache de paginas autenticadas;
- Lume em Casa;
- Lume Connect;
- worker de automacoes;
- WhatsApp Web com sessao QR e fila de mensagens;
- auditoria e notificacoes internas.

## Ativo com configuracao externa

- SMTP/Brevo para e-mails reais;
- checkout Asaas atras de flags e homologacao;
- assinatura `.ics` do Google Agenda;
- uploads e processamento de video quando `ffmpeg`/`ffprobe` estao presentes.

## Pausado

- app Flutter em `apps/lume_app/` para Android/iOS;
- shell desktop Electron em `desktop/`;
- OAuth e sincronizacao bidirecional do Google Agenda;
- integracao oficial Meta/WhatsApp.

Itens pausados permanecem versionados, mas nao participam do deploy web. O
Flutter possui workflow proprio que so dispara quando seu diretorio muda.

## Futuro ou condicionado a decisao

- retomada e publicacao do app mobile;
- IA externa para geracao de legendas;
- publicacao oficial em redes sociais;
- modulo fiscal completo e integracoes fiscais externas;
- ativacao definitiva do checkout Asaas apos sandbox e credenciais;
- estrategia SaaS/multiclinica alem da operacao atual.

## Criterio para mudar status

Uma funcionalidade passa para **ativa** somente quando codigo, migration,
permissoes, testes, documentacao e operacao estiverem coerentes. Integracoes
externas exigem ainda credenciais, webhook/OAuth, teste de falha e observacao
de logs. Interface visivel sem backend ou credencial nao conta como ativa.
