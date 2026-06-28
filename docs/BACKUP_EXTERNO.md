# Backup externo da VPS

O backup local da VPS e necessario, mas nao e suficiente. Se a VPS falhar, for apagada ou tiver problema de disco, a copia local tambem pode ser perdida. Mantenha uma copia externa em Google Drive, S3, Backblaze B2, Cloudflare R2 ou storage equivalente.

## 1. Backup local

Na VPS:

```bash
cd /srv/lume-gestao
sh scripts/backup-production.sh
```

Arquivos gerados:

```text
backups/lume_db_YYYYMMDD_HHMMSS.sql
backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
```

## 2. Instalar rclone

Na VPS:

```bash
sudo apt update
sudo apt install -y rclone
```

Configure o remote seguindo o provedor escolhido:

```bash
rclone config
```

Exemplos de destino:

```text
gdrive:lume-gestao/backups
b2:lume-gestao/backups
r2:lume-gestao/backups
```

## 3. Ativar upload externo

No arquivo `.env` real da VPS, adicione ou ajuste:

```text
BACKUP_UPLOAD_ENABLED=True
BACKUP_RCLONE_REMOTE=gdrive:lume-gestao/backups
BACKUP_RCLONE_FLAGS=--transfers 2 --checkers 4
```

Nao coloque token, senha ou arquivo de credenciais no Git. O `rclone config` guarda esses dados fora do repositorio.

## 4. Testar

Na VPS:

```bash
cd /srv/lume-gestao
sh scripts/backup-production.sh
rclone ls gdrive:lume-gestao/backups
```

Troque `gdrive:lume-gestao/backups` pelo remote escolhido.

## 5. Cron diario

Na VPS:

```bash
crontab -e
```

Exemplo diario as 03:00:

```text
0 3 * * * cd /srv/lume-gestao && sh scripts/backup-production.sh >> backups/backup.log 2>&1
```

## 6. Retencao e restauracao

O script remove arquivos locais antigos conforme `RETENTION_DAYS`, mas nao apaga automaticamente o storage externo. Configure a retencao no provedor ou crie uma regra separada no rclone.

Antes de usar dados reais por muito tempo, faca uma restauracao de teste em ambiente separado:

```bash
sh scripts/restore-production.sh backups/lume_db_YYYYMMDD_HHMMSS.sql backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
```
