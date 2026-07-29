# Gateway WhatsApp Baileys (candidato)

Serviço interno e opt-in da Fase 3. O Django continua usando o transporte
`legacy` por padrão. A versão `baileys@7.0.0-rc14` está fixada exatamente e,
por ser release candidate, não está aprovada para corte de produção.

## Requisitos

- Node.js 20 ou superior (a imagem usa Node.js 22);
- PostgreSQL acessível por `DATABASE_URL`;
- `WHATSAPP_GATEWAY_TOKEN`;
- `WHATSAPP_AUTH_ENCRYPTION_KEY` com 32 bytes codificados em base64;
- sessão lógica `clinic-primary` (configurável por `WHATSAPP_SESSION_ID`).

As credenciais de autenticação são persistidas no PostgreSQL com AES-256-GCM.
O logout apaga somente a sessão lógica selecionada e inicia imediatamente uma
nova tentativa de pareamento, deixando um QR disponível para o operador. O QR
é renovado pelo protocolo enquanto a sessão estiver desconectada. O gateway
não registra QR, mensagens, credenciais ou token.

## Execução de homologação

```powershell
docker compose --profile baileys-candidate up --build whatsapp-baileys
```

Para o Django usar o candidato, defina `WHATSAPP_TRANSPORT=baileys` apenas no
ambiente de homologação. Não execute `legacy` e `baileys` para a mesma sessão
como transportes ativos ao mesmo tempo.

O pipeline publica a imagem imutável e atualiza a tag `candidate`, mas não
ativa o perfil na VPS. O corte exige pareamento acompanhado, envio controlado
e período de observação antes de alterar o transporte de produção.
