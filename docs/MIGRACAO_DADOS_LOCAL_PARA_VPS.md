# Migracao de dados locais Docker Linux para VPS

Este roteiro serve para migrar os dados preenchidos no notebook Linux da clinica para a VPS em producao.

## Onde executar cada comando

Existem tres ambientes diferentes nesta migracao:

- **Seu Windows**: o computador que voce esta usando agora. Use PowerShell/Terminal do Windows para abrir SSH ou copiar arquivos quando indicado.
- **Notebook Linux da clinica via AnyDesk**: o computador da sua irma onde ela ja preencheu pacientes, agenda e outros dados. Os comandos marcados como "no notebook Linux dela" devem ser executados no terminal desse notebook, acessado pelo AnyDesk.
- **VPS**: o servidor Ubuntu em `187.127.37.208`. Quando o roteiro disser "na VPS", significa executar o comando dentro de uma sessao SSH conectada ao servidor. Voce pode abrir essa sessao a partir do seu Windows com:

```powershell
ssh root@187.127.37.208
```

Depois que estiver logado, o prompt passa a ser da VPS. A partir dai, os comandos "na VPS" rodam no servidor, nao no seu Windows.

## Resposta curta

Se a clinica passar a usar a VPS sem migracao, os dados digitados no notebook Linux nao aparecerao na VPS.

Eles nao estao necessariamente perdidos. Normalmente ficam dentro do volume Docker local do PostgreSQL e, possivelmente, na pasta `media` do projeto local.

Nao rode `docker compose down -v` no notebook dela. Esse comando pode apagar o volume do banco local.

## Estrategia mais segura

Vamos tratar o banco local do notebook como a fonte dos dados reais iniciais e substituir o banco vazio/recem-criado da VPS por ele.

Como a VPS acabou de ser criada e ainda tem poucos dados reais, essa e a melhor janela para fazer a migracao.

## Antes de comecar

No notebook Linux dela:

- Nao atualizar o codigo ainda.
- Nao apagar containers.
- Nao apagar volumes.
- Nao rodar `docker compose down -v`.
- Parar o uso do sistema enquanto gera o backup para evitar dados no meio do caminho.

Na VPS:

- Fazer backup antes da restauracao.
- Parar `web` e `worker` durante a restauracao.
- Manter o `db` rodando.

## 1. Descobrir o nome dos containers no notebook Linux

Onde executar: **notebook Linux da clinica via AnyDesk**.

No notebook dela, dentro da pasta do projeto:

```bash
docker compose ps
```

Se o projeto estiver igual ao ambiente de desenvolvimento, deve existir um servico chamado `db`.

## 2. Criar uma pasta de exportacao no notebook Linux

```bash
mkdir -p ~/lume-migracao
```

## 3. Gerar dump do banco local

Onde executar: **notebook Linux da clinica via AnyDesk**.

Na pasta do projeto local do notebook:

```bash
docker compose exec -T db sh -c 'pg_dump -U "${POSTGRES_USER:-lume}" "${POSTGRES_DB:-lume}"' > ~/lume-migracao/lume_local_db.sql
```

Se esse comando falhar por variaveis vazias, use o padrao do compose de desenvolvimento, ainda no notebook Linux dela:

```bash
docker compose exec -T db sh -c 'pg_dump -U lume lume' > ~/lume-migracao/lume_local_db.sql
```

Conferir se o arquivo foi criado:

```bash
ls -lh ~/lume-migracao/lume_local_db.sql
```

## 4. Compactar arquivos de media/uploads locais

Onde executar: **notebook Linux da clinica via AnyDesk**.

Na pasta do projeto local do notebook:

```bash
if [ -d media ]; then
  tar -czf ~/lume-migracao/lume_local_media.tar.gz media
else
  tar -czf ~/lume-migracao/lume_local_media.tar.gz --files-from /dev/null
fi
```

Conferir:

```bash
ls -lh ~/lume-migracao/lume_local_media.tar.gz
```

## 5. Copiar arquivos para a VPS

Onde executar: **notebook Linux da clinica via AnyDesk**.

No notebook Linux dela:

```bash
scp ~/lume-migracao/lume_local_db.sql root@187.127.37.208:/srv/lume-gestao/data/backups/lume_local_db.sql
scp ~/lume-migracao/lume_local_media.tar.gz root@187.127.37.208:/srv/lume-gestao/data/backups/lume_local_media.tar.gz
```

Se o acesso SSH da maquina dela ainda nao estiver autorizado, usar senha da VPS ou adicionar chave publica dela em `/root/.ssh/authorized_keys`.

## 6. Fazer backup da VPS antes de restaurar

Onde executar: **VPS**, dentro de uma sessao SSH aberta a partir do seu Windows.

Na VPS:

```bash
cd /srv/lume-gestao
BACKUP_DIR=/srv/lume-gestao/data/backups RETENTION_DAYS=14 sh scripts/backup-production.sh
```

## 7. Parar web e worker na VPS

Onde executar: **VPS**, dentro de uma sessao SSH aberta a partir do seu Windows.

Na VPS:

```bash
cd /srv/lume-gestao
docker compose -f docker-compose.prod.yml stop web worker
```

## 8. Restaurar banco na VPS

Atencao: este passo substitui o conteudo atual do banco da VPS.

Onde executar: **VPS**, dentro de uma sessao SSH aberta a partir do seu Windows.

Na VPS:

```bash
cd /srv/lume-gestao
docker compose -f docker-compose.prod.yml exec -T db sh -c 'dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" --if-exists'
docker compose -f docker-compose.prod.yml exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
cat /srv/lume-gestao/data/backups/lume_local_db.sql | docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## 9. Restaurar media na VPS

Onde executar: **VPS**, dentro de uma sessao SSH aberta a partir do seu Windows.

Na VPS:

```bash
cd /srv/lume-gestao
mkdir -p data/media
tar -xzf /srv/lume-gestao/data/backups/lume_local_media.tar.gz -C data
```

Se o arquivo compactado tiver sido criado vazio porque nao havia media, esse passo pode nao adicionar arquivos.

## 10. Subir app e aplicar migracoes

Onde executar: **VPS**, dentro de uma sessao SSH aberta a partir do seu Windows.

Na VPS:

```bash
cd /srv/lume-gestao
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate
docker compose -f docker-compose.prod.yml ps
```

## 11. Validar producao

Onde executar: **VPS ou seu Windows**.

Na VPS ou no seu computador Windows:

```bash
curl -I https://sistema.clinicafisiolume.com.br/healthz/
```

No navegador:

```text
https://sistema.clinicafisiolume.com.br/login/
```

Conferir manualmente:

- pacientes cadastrados;
- profissionais;
- agenda;
- pacotes;
- financeiro;
- prontuarios;
- fotos/anexos, se existirem;
- usuarios e permissoes.

## 12. Senhas e usuarios depois da migracao

Se o dump local tiver usuarios antigos, eles tambem serao migrados.

Se precisar redefinir a senha do admin depois da restauracao:

```bash
cd /srv/lume-gestao
docker compose -f docker-compose.prod.yml exec web python manage.py changepassword admin
```

## 13. Plano de rollback

Se algo der errado:

1. Parar `web` e `worker`.
2. Restaurar o backup da VPS feito no passo 6.
3. Subir os containers novamente.

Usar o script:

```bash
cd /srv/lume-gestao
sh scripts/restore-production.sh /srv/lume-gestao/data/backups/lume_db_YYYYMMDD_HHMMSS.sql /srv/lume-gestao/data/backups/lume_media_YYYYMMDD_HHMMSS.tar.gz
docker compose -f docker-compose.prod.yml restart web worker
```

## Observacao final

Nao fazer essa migracao durante uso ativo da clinica. O ideal e escolher uma janela curta, exportar o banco local, restaurar na VPS e entao orientar que todos passem a usar somente a URL publica.
