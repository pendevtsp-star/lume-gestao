# Instalacao resumida

Este e o roteiro mais curto para instalar o Lume Gestao em cada sistema operacional.

## Windows

- baixe a release desktop em `https://github.com/pendevtsp-star/lume-gestao/releases`;
- execute o instalador `.exe`;
- abra `Lume Gestao` pelo menu Iniciar;
- os dados locais ficam em `%APPDATA%/Lume Gestao/backend-data`.

## macOS

- baixe a release desktop `.dmg`;
- arraste `Lume Gestao` para `Applications`;
- se o macOS bloquear a primeira abertura, use `Open Anyway`;
- os dados locais ficam em `~/Library/Application Support/Lume Gestao/backend-data`.

## Linux desktop

- baixe a release `.AppImage` ou `.deb`;
- instale e abra o aplicativo;
- os dados locais ficam em `~/.config/Lume Gestao/backend-data`.

## Linux ou Windows como servidor local

- clone o repositorio;
- copie `.env.clinic.example` para `.env`;
- ajuste `SECRET_KEY`, `POSTGRES_PASSWORD`, `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`;
- suba com `docker compose up --build -d`.
- o compose sobe tambem o `worker`, que processa mensagens WhatsApp agendadas.

## Atualizacoes

- o app desktop fica preparado para verificar novas versoes publicadas nas releases do GitHub;
- a pipeline `.github/workflows/desktop-release.yml` gera os instaladores por sistema;
- a pipeline `.github/workflows/ci.yml` valida checks e testes do backend antes das entregas.
