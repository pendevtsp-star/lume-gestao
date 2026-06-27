# Checklist de seguranca

Este checklist resume as verificacoes recomendadas antes de liberar o Lume Gestao para uso real com pacientes e dados financeiros.

## Autenticacao e sessoes

- Exigir senhas fortes para administradores, gerentes e profissionais.
- Trocar credenciais padrao antes de entregar para usuario final.
- Validar recuperacao de senha por e-mail com token temporario.
- Confirmar `CSRF` ativo em todos os formularios que alteram dados.
- Definir tempo de sessao adequado para computadores compartilhados na clinica.

## Permissoes por perfil

- Conferir se paciente acessa apenas seus proprios dados, agenda e solicitacoes.
- Conferir se profissional acessa apenas pacientes atendidos por ele ou autorizados.
- Conferir se gerente/admin acessa relatorios, financeiro, fiscal e integracoes.
- Garantir que toda regra de permissao exista no backend, nao apenas no menu/template.
- Testar URLs diretas de exclusao, edicao, relatorios, fiscal e integracoes com usuarios sem permissao.

## Dados sensiveis

- Revisar campos com CPF, telefone, e-mail, prontuario, pagamentos e documentos fiscais.
- Evitar gravar tokens, secrets e senhas em logs, commits ou mensagens de erro.
- Manter `.env`, banco local, `media/`, backups e arquivos gerados fora do Git.
- Definir rotina de backup local e restauracao testada.
- Avaliar criptografia de disco na maquina local onde o banco sera instalado.

## Integracoes

- Validar que Google Client Secret, Meta App Secret e tokens ficam apenas em variaveis de ambiente ou banco protegido.
- Testar desconexao de Google Agenda e WhatsApp removendo tokens ativos.
- Validar modo teste do WhatsApp antes de disparos reais.
- Confirmar logs de mensagens sem expor conteudo sensivel alem do necessario.
- Validar callback OAuth com URL permitida e sem redirecionamento aberto.

## Backend e API

- Rodar testes de permissao para cada view critica.
- Validar dados de entrada em forms/services, principalmente valores financeiros, datas e IDs.
- Confirmar que exclusoes/desativacoes passam por `POST` quando alteram estado.
- Revisar endpoints de exportacao PDF, e-mail e WhatsApp para impedir acesso indevido.
- Conferir rate limit ou protecao operacional para envios em massa e login.

## Deploy e ambiente

- Usar `DEBUG=False` em producao.
- Configurar `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e HTTPS.
- Definir `SECRET_KEY` unica e fora do repositorio.
- Usar banco com usuario e senha fortes.
- Configurar backups, logs e monitoramento do worker.
- Verificar headers de seguranca: HSTS, X-Frame-Options, X-Content-Type-Options e cookies seguros.

## Auditoria

- Registrar acoes sensiveis: login, edicao/exclusao de paciente, financeiro, fiscal, agenda e integracoes.
- Exibir relatorio de auditoria apenas para perfis autorizados.
- Manter data, usuario, objeto alterado e resumo de mudancas.
- Testar busca/filtro do relatorio de auditoria.
- Definir politica de retencao de logs.

