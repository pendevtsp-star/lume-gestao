# Politicas LGPD e onboarding

Este documento resume a base operacional criada para privacidade, consentimentos e primeiro acesso no Lume Gestao.

## Paginas publicas

- `/termos-de-uso/`: regras basicas de uso do sistema.
- `/privacidade/`: dados tratados, finalidades, compartilhamentos e direitos do titular.
- `/consentimento-lgpd/`: consentimento especifico para dados de saude e outros dados sensiveis.

Estas paginas sao acessiveis sem login para que pacientes possam ler antes ou durante o primeiro acesso.

## Consentimentos registrados

No primeiro acesso, o usuario precisa:

- Criar uma nova senha com pelo menos 8 caracteres.
- Aceitar os Termos de Uso.
- Aceitar a Politica de Privacidade.
- Consentir o tratamento de dados de saude para atendimento e gestao da clinica.

O sistema registra data/hora e versao do consentimento no perfil do usuario.

## Primeiro acesso de pacientes

Ao cadastrar um novo paciente, o sistema cria automaticamente um usuario vinculado ao paciente.

Fluxo de entrega:

1. Se houver e-mail, envia credenciais por SMTP.
2. Se nao houver e-mail, tenta enviar pelo WhatsApp cadastrado.
3. Se nenhum canal funcionar, o sistema mostra login e senha temporaria para entrega manual por gerente/admin.

A senha temporaria e aleatoria. O sistema nao usa senha previsivel como `primeironome123`.

Para pacientes ja cadastrados antes desta funcionalidade, use:

```bash
python manage.py ensure_patient_users
python manage.py ensure_patient_users --commit
```

O primeiro comando apenas simula. O segundo cria usuarios e tenta enviar as credenciais.

## Recuperacao de senha

O fluxo `/recuperar-senha/` aceita login ou e-mail.

- Se houver e-mail, envia link tradicional de redefinicao.
- Se nao houver e-mail e houver WhatsApp, gera uma senha temporaria e exige troca no proximo login.
- Se o WhatsApp estiver em modo teste/dry-run, a senha nao e alterada de verdade.

## Controle de acesso a dados sensiveis

O acesso segue os perfis do sistema:

- Paciente: ve os proprios dados permitidos.
- Profissional: ve pacientes relacionados aos seus atendimentos/vinculos.
- Administracao/Gerencia: acessa gestao operacional.
- Visualizacao: bloqueado para alteracoes por middleware.

Toda validacao relevante deve continuar passando pelo backend.

## Pendencias antes de producao ampla

- Validar textos com assessoria juridica.
- Definir canal oficial para solicitacoes de titulares.
- Definir prazos de retencao e descarte.
- Revisar permissoes por perfil com dados reais.
- Garantir SMTP e WhatsApp reais antes de depender dos envios automaticos.
- Testar restauracao de backup com dados anonimizados.

## Referencias oficiais para revisao

- Lei Geral de Protecao de Dados Pessoais, Lei 13.709/2018.
- Guias e materiais da Autoridade Nacional de Protecao de Dados (ANPD).
