# Instalacao de teste na maquina da clinica

Este roteiro sobe o Lume Gestao em uma maquina da clinica usando Docker e PostgreSQL local. Nao e necessario criar conta externa no PostgreSQL: o banco roda dentro do Docker.

## 1. Preparar a maquina

Instale:

- Docker Desktop
- Git for Windows

Depois reinicie a maquina se o instalador do Docker pedir.

## 2. Obter o sistema

Quando as alteracoes estiverem no GitHub:

```powershell
cd C:\
git clone https://github.com/pendevtsp-star/lume-gestao.git
cd C:\lume-gestao
```

Se ainda nao tivermos enviado as alteracoes para o GitHub, use um pacote `.zip` gerado a partir desta maquina de desenvolvimento e extraia em `C:\lume-gestao`.

## 3. Criar configuracao local

Na primeira execucao, rode:

```powershell
.\scripts\clinic-up.ps1
```

O script criara um arquivo `.env` e pedira para editar. Abra o `.env` e ajuste:

```text
SECRET_KEY=uma-chave-grande-e-unica
ALLOWED_HOSTS=127.0.0.1,localhost,IP_DA_MAQUINA_DA_CLINICA
CSRF_TRUSTED_ORIGINS=http://IP_DA_MAQUINA_DA_CLINICA:8000
POSTGRES_PASSWORD=uma-senha-forte-do-banco
LUME_SEED_DEMO=True
```

Para descobrir o IP da maquina da clinica:

```powershell
ipconfig
```

Use o IPv4 da rede local, por exemplo `192.168.0.50`.

Durante testes, mantenha `LUME_SEED_DEMO=True` para criar os usuarios demonstrativos. Quando a clinica for usar dados reais, altere para:

```text
LUME_SEED_DEMO=False
```

## 4. Subir o sistema

Depois de editar o `.env`:

```powershell
.\scripts\clinic-up.ps1
```

Na propria maquina:

```text
http://127.0.0.1:8000
```

Em outro computador da mesma rede:

```text
http://IP_DA_MAQUINA_DA_CLINICA:8000
```

Se nao abrir de outro computador, libere a porta `8000` no Firewall do Windows.

## 5. Usuarios de teste

Se `LUME_SEED_DEMO=True`, os acessos iniciais sao:

```text
Gerencia: admin / Lume@12345
Administracao: recepcao / Recepcao@123
Profissional: helena / Helena@123
Paciente: marina / Marina@123
```

Troque as senhas antes de qualquer uso com dados reais.

## 6. Parar o sistema

```powershell
.\scripts\clinic-stop.ps1
```

Os dados permanecem salvos no volume Docker.

## 7. Backup

Rode periodicamente:

```powershell
.\scripts\clinic-backup.ps1
```

Os arquivos serao criados na pasta `backups/`.
