# Instalacao no macOS

Este roteiro cobre o uso do Lume Gestao como aplicativo desktop no macOS.

## 1. Baixar a release

Quando a release desktop estiver publicada, baixe o arquivo `.dmg` em:

```text
https://github.com/pendevtsp-star/lume-gestao/releases
```

## 2. Instalar

Abra o `.dmg` e arraste `Lume Gestao` para `Applications`.

## 3. Primeiro uso no macOS

Como as builds de teste podem sair sem assinatura da Apple, o macOS pode bloquear a primeira abertura.

Se isso acontecer:

1. Abra `System Settings`
2. Entre em `Privacy & Security`
3. Procure o aviso sobre `Lume Gestao`
4. Clique em `Open Anyway`

Outra forma:

```text
Control + click no app > Open
```

## 4. Funcionamento local

Ao abrir, o app:

- inicia o backend local automaticamente;
- usa banco SQLite local na pasta do usuario;
- salva uploads e arquivos do sistema na pasta local do aplicativo.

Nao e necessario instalar PostgreSQL para o modo desktop.

Caminho esperado dos dados locais:

```text
~/Library/Application Support/Lume Gestao/backend-data
```

## 5. Atualizacoes

O app fica preparado para verificar novas versoes publicadas nas releases do GitHub e avisar o usuario quando houver atualizacao disponivel.
Enquanto estiver aberto, o proprio app tambem processa a fila local de mensagens WhatsApp agendadas.

## 6. Build local para testes

Se voce quiser gerar o app macOS em uma maquina Apple:

```bash
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd lume-gestao
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
```

Depois gere o backend local:

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

E por fim o pacote macOS:

```bash
cd desktop
npm install
npm run dist:mac
```

Os artefatos saem em:

```text
dist/desktop
```
