# Instalacao em outra maquina Linux

Este roteiro cobre duas formas de levar o Lume para outra maquina Linux:

- rodar o sistema web/local via Docker, recomendado para uma maquina da clinica ou servidor local;
- gerar um pacote desktop Linux, quando a ideia for instalar como aplicativo grafico.

## Opcao 1: Linux via Docker

Use esta opcao se a maquina Linux vai hospedar o sistema e outras maquinas vao acessar pelo navegador.

### 1. Preparar a maquina Linux

Em Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Saia e entre novamente na sessao para o grupo `docker` aplicar.

Teste:

```bash
docker --version
docker compose version
```

### 2. Baixar o projeto do GitHub

```bash
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd lume-gestao
```

### 3. Criar o arquivo de ambiente

```bash
cp .env.example .env
nano .env
```

Exemplo para rede local:

```text
DEBUG=True
SECRET_KEY=troque-por-uma-chave-grande
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.0.50
CSRF_TRUSTED_ORIGINS=
DB_ENGINE=postgres
POSTGRES_DB=lume
POSTGRES_USER=lume
POSTGRES_PASSWORD=troque-esta-senha
POSTGRES_HOST=db
POSTGRES_PORT=5432
LUME_SEED_DEMO=True
```

Troque `192.168.0.50` pelo IP da maquina Linux.

Descobrir o IP:

```bash
hostname -I
```

### 4. Subir o sistema

```bash
docker compose up --build -d
```

Ver logs:

```bash
docker compose logs -f web
```

### 5. Acessar

Na propria maquina Linux:

```text
http://127.0.0.1:8000
```

De outro computador na mesma rede:

```text
http://192.168.0.50:8000
```

### 6. Liberar firewall, se necessario

Se usar `ufw`:

```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

### 7. Parar, atualizar e reiniciar

Parar:

```bash
docker compose down
```

Atualizar codigo:

```bash
git pull
docker compose up --build -d
```

## Opcao 2: levar uma copia completa sem Git

Use esta opcao quando a maquina Linux nao vai clonar do GitHub.

No Windows, crie um `.zip` do projeto sem pastas pesadas/locais:

```powershell
Compress-Archive `
  -Path accounts,billing,config,core,desktop,docs,patients,reports,scheduling,scripts,static,team,templates,Dockerfile,docker-compose.yml,manage.py,README.md,requirements.txt,.env.example,.env.clinic.example,.dockerignore `
  -DestinationPath dist\lume-gestao-codigo.zip `
  -Force
```

Copie `dist\lume-gestao-codigo.zip` para a maquina Linux.

No Linux:

```bash
sudo apt update
sudo apt install -y unzip docker.io docker-compose-plugin
unzip lume-gestao-codigo.zip -d lume-gestao
cd lume-gestao
cp .env.example .env
nano .env
docker compose up --build -d
```

Nao copie `.venv`, `node_modules`, `db.sqlite3`, `media` ou `dist` como base de instalacao. Esses itens sao locais da maquina de desenvolvimento ou dados sensiveis.

## Opcao 3: gerar app desktop Linux

Use esta opcao se voce quer um aplicativo Linux instalavel, por exemplo `.AppImage` ou `.deb`.

Importante: o build Linux deve ser feito em uma maquina Linux.

### 1. Preparar dependencias

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm
```

### 2. Clonar e preparar Python

```bash
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd lume-gestao
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
```

### 3. Gerar o backend local Linux

```bash
rm -rf desktop/backend-bin
pyinstaller \
  --name lume-backend \
  --onedir \
  --distpath desktop/backend-bin \
  --workpath dist/pyinstaller-work \
  --specpath dist/pyinstaller-spec \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --collect-all django \
  --collect-all rest_framework \
  --collect-all django_filters \
  --collect-submodules config \
  --collect-submodules accounts \
  --collect-submodules billing \
  --collect-submodules core \
  --collect-submodules patients \
  --collect-submodules reports \
  --collect-submodules scheduling \
  --collect-submodules team \
  desktop/backend_entry.py
```

### 4. Gerar o app Linux

```bash
cd desktop
npm install
npm run dist:linux
```

Os arquivos saem em:

```text
dist/desktop
```

## Backup

No Docker, os dados ficam no volume `postgres_data`. Para backup simples:

```bash
docker compose exec db pg_dump -U lume lume > lume-backup.sql
```

No app desktop, os dados ficam na pasta de dados do usuario do sistema operacional.
