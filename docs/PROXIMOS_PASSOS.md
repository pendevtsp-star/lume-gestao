# Proximos passos salvos

Este documento guarda os proximos passos combinados para retomarmos depois dos itens 1 e 2.

## 3. Integracao oficial com Google Agenda

Estado atual: a agenda exporta arquivo `.ics`, que pode ser importado ou assinado pelo Google Agenda.

Proximo passo: implementar OAuth do Google, salvar credenciais por clinica/usuario autorizado e sincronizar criacao, reagendamento e cancelamento de eventos.

## 4. Envio real por WhatsApp

Estado atual: usuarios de administracao e gerencia podem cadastrar um numero de WhatsApp para avisos futuros.

Proximo passo: escolher provedor, como Meta Cloud API, Twilio ou outro gateway, e criar modulo de notificacoes para pacientes e profissionais.

## 5. Reforco de seguranca e permissoes por objeto

Estado atual: a API e as telas ja filtram dados por perfil em pontos criticos.

Proximo passo: revisar todos os endpoints com matriz de permissao, ampliar testes de tentativa de acesso indevido e padronizar respostas para objetos bloqueados.

## 6. Versao mobile

Estado atual: existe modulo `mobile` com endpoint inicial de bootstrap.

Proximo passo: criar rotas/payloads especificos para agenda, perfil, creditos, pagamentos e prontuario permitido, pensando em app do paciente e app/area do profissional.

## 7. Implantacao de teste na clinica

Estado atual: existe roteiro Docker + PostgreSQL local.

Proximo passo: preparar a maquina da clinica com `.env` real, e-mail SMTP, backup periodico e usuarios sem dados demonstrativos quando os testes comecarem com informacoes reais.
