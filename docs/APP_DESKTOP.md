# App desktop

## Decisao tecnica

A primeira versao desktop usa Electron encapsulando a interface web Django existente e iniciando o backend local como processo filho.

Motivos:

- Mantem a UI e as regras ja feitas no Django, sem reescrever tudo agora.
- Entrega instaladores para Windows, macOS e Linux com `electron-builder`.
- Permite manter o backend local nesta fase e trocar a origem para uma API hospedada depois.
- Facilita uma futura convivencia com app mobile, porque a API REST atual continua sendo o contrato principal.

Tauri continua sendo uma boa alternativa quando o app estiver mais maduro e houver tempo para resolver o empacotamento multiplataforma do Python com mais rigor. Flutter Desktop so faria sentido se a UI fosse reescrita em Flutter pensando em compartilhar telas com o mobile.

## Desenvolvimento

Na raiz do projeto, prepare o ambiente Python normalmente:

```powershell
.\scripts\dev.ps1
```

Em outro terminal:

```powershell
cd desktop
npm install
npm start
```

O Electron inicia o backend local em `127.0.0.1:18780` e abre a janela do sistema.
Enquanto o app estiver aberto, ele tambem processa localmente a fila de mensagens WhatsApp agendadas.

## Dados locais

Quando `LUME_DESKTOP=True`, o Django salva:

- `db.sqlite3` na pasta de dados do usuario do aplicativo.
- uploads em `backend-data/media`.

Isso evita gravar dados dentro da pasta instalada do programa.

Caminhos esperados por sistema operacional:

- Windows: `%APPDATA%/Lume Gestao/backend-data`
- macOS: `~/Library/Application Support/Lume Gestao/backend-data`
- Linux: `~/.config/Lume Gestao/backend-data`

## Atualizacoes automaticas

O desktop agora esta preparado para usar `electron-updater` com releases do GitHub.

Fluxo previsto:

1. publicar uma tag no formato `desktop-vX.Y.Z`;
2. o GitHub Actions gera os instaladores por sistema operacional;
3. os artefatos sao publicados na release;
4. o app verifica atualizacoes em segundo plano e avisa o usuario quando houver nova versao pronta.

Workflow versionado:

```text
.github/workflows/desktop-release.yml
```

Observacoes:

- builds de teste podem funcionar sem assinatura de codigo;
- para distribuicao publica em larga escala, o ideal continua sendo assinar Windows e macOS;
- se futuramente quisermos canal beta/estavel, o `electron-updater` ja deixa isso preparado.
- no modo desktop, os jobs locais do WhatsApp usam `LUME_JOB_INTERVAL_SECONDS`, por padrao a cada 60 segundos.

## Icone do app

O app agora usa a arte institucional da Lume como base para os icones de Windows, macOS e Linux.

Arquivos gerados:

```text
desktop/build/icon.ico
desktop/build/icon.icns
desktop/build/icon.png
desktop/build/icons/
```

Para regenerar os icones:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_desktop_icons.py "C:\caminho\da\sua\imagem.png"
```

## Assinatura de codigo

O pipeline desktop ficou preparado para assinatura automatica no GitHub Actions.

Segredos recomendados para Windows:

```text
WIN_CSC_LINK
WIN_CSC_KEY_PASSWORD
```

Segredos recomendados para macOS:

```text
CSC_LINK
CSC_KEY_PASSWORD
APPLE_ID
APPLE_APP_SPECIFIC_PASSWORD
APPLE_TEAM_ID
```

Opcionalmente, voce tambem pode usar o fluxo com chave da Apple:

```text
APPLE_API_KEY
APPLE_API_KEY_ID
APPLE_API_ISSUER
```

Observacoes praticas:

- sem certificado, o build continua funcionando, mas sai sem assinatura;
- com os segredos preenchidos, o workflow `desktop-release.yml` passa a tentar assinar automaticamente;
- no macOS, a notarizacao fica preparada junto da assinatura por causa do `hardenedRuntime` e das variaveis Apple.

## Build instalavel no Windows

```powershell
.\scripts\build-desktop.ps1
```

O script:

- instala dependencias Python na `.venv`;
- gera um backend local com PyInstaller em `desktop/backend-bin`;
- instala dependencias Node do Electron;
- gera o instalador Windows em `dist/desktop`.

Em builds locais sem certificado de assinatura, o executavel Windows e gerado sem assinatura de codigo. Para distribuicao publica, o ideal e assinar o instalador com certificado proprio.

Para macOS e Linux, rode o mesmo conceito em uma maquina do respectivo sistema:

```bash
cd desktop
npm install
npm run dist:mac
# ou
npm run dist:linux
```

Na pratica, builds de macOS devem ser feitos no macOS. Builds Linux devem ser feitos no Linux. Builds Windows podem ser feitos no Windows.

## Preparacao para VPS

O projeto ja esta em boa direcao para VPS porque possui Docker, PostgreSQL e variaveis de ambiente. Para producao, a recomendacao e:

- Django + Gunicorn;
- PostgreSQL gerenciado pelo proprio servidor ou por servico externo;
- Nginx como proxy reverso e TLS;
- backups automaticos do banco e da pasta `media`;
- `DEBUG=False`, `SECRET_KEY` forte, `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` configurados.

## Servidor recomendado

Para custo-beneficio inicial, eu usaria uma VPS Linux simples com 2 vCPU, 2 a 4 GB de RAM e 40 GB ou mais de SSD.

Boas opcoes:

- Hetzner Cloud: costuma ter o melhor custo-beneficio bruto, especialmente na Europa.
- DigitalOcean: mais cara, mas muito simples de operar e com boa documentacao.
- Vultr: intermediaria, com varias regioes.
- AWS Lightsail: boa se a prioridade for ficar dentro do ecossistema AWS, mas geralmente menos competitiva no preco.

Minha recomendacao pratica: Hetzner se a latencia Brasil-Europa for aceitavel para a clinica; DigitalOcean ou Vultr se simplicidade operacional e regioes mais proximas pesarem mais. Para uma clinica usando poucos usuarios simultaneos, comece pequeno e aumente quando houver sinais reais de uso.

Nota revisada em 25/06/2026:

- Hetzner CX22/CX23 segue forte em custo-beneficio para 2 vCPU e 4 GB.
- DigitalOcean Basic com 2 GB/1 vCPU aparece na faixa de US$ 12/mes e 2 GB/2 vCPU na faixa de US$ 18/mes.
- AWS Lightsail Linux `Small-2GB` aparece em US$ 10/mes no bundle IPv6-only, mas a decisao depende de rede, backups e banco.

Links de referencia: [Hetzner Cloud](https://www.hetzner.com/cloud), [DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets), [AWS Lightsail bundles](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html).
