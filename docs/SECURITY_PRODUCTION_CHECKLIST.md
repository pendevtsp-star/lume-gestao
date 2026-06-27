# Checklist de seguranca para dados reais

Use este checklist antes de cadastrar pacientes reais, prontuarios, pagamentos ou documentos fiscais no Lume Gestao em producao.

## Ambiente e Django

- [ ] `DEBUG=False` no `.env` real da VPS.
- [ ] `SECRET_KEY` forte, unica, com mais de 50 caracteres e fora do Git.
- [ ] `ALLOWED_HOSTS=sistema.clinicafisiolume.com.br`.
- [ ] `CSRF_TRUSTED_ORIGINS=https://sistema.clinicafisiolume.com.br`.
- [ ] `PUBLIC_BASE_URL=https://sistema.clinicafisiolume.com.br`, quando usado para links absolutos.
- [ ] `LUME_STRICT_PRODUCTION=True`.
- [ ] `LUME_SEED_DEMO=False`.
- [ ] Dados demonstrativos removidos antes do uso real.

## HTTPS, Cloudflare e rede

- [ ] HTTPS funcionando com certificado valido.
- [ ] Registro `A sistema -> IP_DA_VPS` criado na Cloudflare sem IP fixo no codigo.
- [ ] Cloudflare mantida em `DNS only` ate Nginx e HTTPS estarem funcionando na VPS.
- [ ] Cloudflare em modo SSL/TLS `Full (strict)` depois da validacao de HTTPS na VPS.
- [ ] Porta `8000` nao exposta publicamente; app acessivel apenas via Nginx.
- [ ] `docker-compose.prod.yml` publica `127.0.0.1:8000:8000`, nao `0.0.0.0:8000:8000`.
- [ ] Firewall ativo liberando apenas o necessario, normalmente `22`, `80` e `443`.
- [ ] SSH usando usuario nao-root com `sudo`.
- [ ] Login SSH por chave configurado quando possivel.
- [ ] `/healthz/` responde HTTP 200 via HTTPS.

## Usuarios e permissoes

- [ ] Cada pessoa usa usuario individual, sem senha compartilhada.
- [ ] Senhas padrao e usuarios de teste foram removidos ou tiveram senha trocada.
- [ ] Perfis de paciente, profissional, administracao e gerencia revisados.
- [ ] Permissoes por perfil revisadas no backend, nao apenas no menu visual.
- [ ] Paciente acessa apenas dados proprios.
- [ ] Profissional acessa apenas pacientes e prontuarios permitidos.
- [ ] Financeiro, fiscal, relatorios, auditoria e integracoes restritos a perfis autorizados.

## Integracoes

- [ ] SMTP real configurado e testado.
- [ ] Recuperacao de senha envia e-mail real.
- [ ] Google Calendar configurado apenas com credenciais reais da clinica.
- [ ] Callback Google autorizado: `https://sistema.clinicafisiolume.com.br/integracoes/google/callback/`.
- [ ] WhatsApp permanece com `WHATSAPP_DRY_RUN=True` ate credenciais, numero e templates serem validados.
- [ ] URLs publicas de futuras integracoes, callbacks ou webhooks usam `https://sistema.clinicafisiolume.com.br`.
- [ ] Tokens e secrets de Google, Meta e e-mail nao aparecem em logs, commits ou prints.

## Dados sensiveis e logs

- [ ] Logs nao exibem CPF, prontuario, tokens, senhas ou conteudo sensivel desnecessario.
- [ ] `.env`, backups, dumps SQL, banco local, `media/`, `data/` e `staticfiles/` continuam ignorados no Git.
- [ ] Uploads de pacientes ficam em volume/diretorio persistente.
- [ ] Acesso ao servidor restrito apenas a pessoas autorizadas.

## Backup, restauracao e rollback

- [ ] Backups diarios configurados com `scripts/backup-production.sh`.
- [ ] Retencao configurada com `RETENTION_DAYS`.
- [ ] Copia externa configurada, por exemplo rclone, S3, Backblaze B2 ou storage equivalente.
- [ ] Teste de restauracao feito em ambiente separado com `scripts/restore-production.sh`.
- [ ] Plano de atualizacao documentado em `docs/UPDATE_PRODUCTION.md`.
- [ ] Plano de rollback testado para voltar a commit anterior.
- [ ] Nunca usar `docker compose down -v` em producao.

## Liberacao final

- [ ] `python manage.py check --deploy` passou com variaveis de producao.
- [ ] `docker compose -f docker-compose.prod.yml config` passou.
- [ ] Containers `db`, `web` e `worker` saudaveis.
- [ ] Nginx validado com `sudo nginx -t`.
- [ ] Checklist revisado por responsavel tecnico antes da entrada de dados reais.
