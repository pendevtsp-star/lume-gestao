# Instalacao no Windows

Este roteiro cobre as duas formas principais de uso no Windows:

- app desktop instalavel, recomendado para usuario final;
- modo navegador com Docker, quando a maquina vai servir o sistema para a rede local.

## Opcao 1: app desktop Windows

### 1. Baixar o instalador

Quando houver uma release publicada no GitHub, baixe o arquivo `.exe` em:

```text
https://github.com/pendevtsp-star/lume-gestao/releases
```

### 2. Instalar

Execute o instalador do `Lume Gestao`.

Se o Windows SmartScreen avisar que o app nao e amplamente reconhecido, clique em:

```text
Mais informacoes > Executar assim mesmo
```

Isso pode acontecer em builds de teste sem assinatura de codigo.

### 3. Abrir o sistema

Depois de instalado, abra `Lume Gestao` pelo menu Iniciar.

O aplicativo:

- sobe um backend local automaticamente;
- salva os dados em banco local SQLite na pasta do usuario;
- salva arquivos enviados dentro da pasta de dados do app.

Caminho esperado dos dados locais:

```text
%APPDATA%/Lume Gestao/backend-data
```

### 4. Atualizacoes

Quando novas versoes forem publicadas como release do GitHub, o desktop passa a verificar atualizacoes automaticamente e avisa o usuario quando houver uma versao pronta para instalar.

## Opcao 2: Windows com Docker

Use esta opcao quando a maquina Windows vai hospedar o sistema para navegacao local ou em rede.

### 1. Instalar dependencias

Instale:

- Docker Desktop
- Git for Windows

### 2. Baixar o projeto

```powershell
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd lume-gestao
copy .env.clinic.example .env
```

### 3. Ajustar configuracao

Edite `.env` e troque principalmente:

```text
SECRET_KEY=uma-chave-grande-e-unica
POSTGRES_PASSWORD=uma-senha-forte
ALLOWED_HOSTS=127.0.0.1,localhost,IP_DA_MAQUINA
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://IP_DA_MAQUINA:8000
```

### 4. Subir

```powershell
docker compose up --build -d
```

Nesse modo, o `docker compose` tambem inicia o servico `worker`, responsavel por processar mensagens WhatsApp agendadas.

### 5. Acessar

Nesta maquina:

```text
http://127.0.0.1:8000
```

Na rede local:

```text
http://IP_DA_MAQUINA:8000
```

## Backup

No app desktop, os dados ficam na pasta de dados do usuario do Windows.

No modo Docker, use:

```powershell
.\scripts\clinic-backup.ps1
```
