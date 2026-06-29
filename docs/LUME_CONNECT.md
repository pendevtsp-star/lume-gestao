# Lume Connect

O Lume Connect e a rede social interna do sistema. Usuarios autenticados e ativos podem publicar posts, curtir e comentar conforme as permissoes ja existentes do modulo.

## Publicacao de video curto

Na tela do feed, use o formulario de publicacao e selecione o campo **Video curto**.

Limites atuais:

- Formatos aceitos: MP4 e MOV.
- Duracao maxima: 60 segundos por padrao (`LUME_CONNECT_MAX_SHORT_VIDEO_SECONDS`).
- Tamanho maximo: 80 MB por padrao (`LUME_CONNECT_MAX_VIDEO_MB`).
- Capa/thumbnail opcional: JPG, JPEG, PNG ou WEBP.

A validacao de duracao desta versao le os metadados do arquivo no backend. Se a duracao nao puder ser confirmada, o upload e bloqueado com mensagem amigavel.

## Comportamento no feed

Videos curtos aparecem em card vertical, com proporcao 9:16, mute inicial e `playsinline`.

O feed usa `IntersectionObserver` para:

- iniciar apenas o video curto mais visivel;
- pausar automaticamente quando o video sai da area visivel;
- manter `preload="metadata"` para reduzir consumo inicial de banda;
- permitir play/pause manual;
- permitir ativar/desativar som;
- repetir automaticamente videos curtos.

Videos comuns continuam renderizando com controles nativos, sem autoplay automatico.

## Armazenamento

Arquivos usam o mecanismo padrao de media do projeto:

- Imagens de posts: `MEDIA_ROOT/lume_connect/posts/`.
- Videos curtos: `MEDIA_ROOT/lume_connect/videos/`.
- Capas de video: `MEDIA_ROOT/lume_connect/video_thumbnails/`.

Em producao, o servidor deve expor `MEDIA_URL` de forma segura, sem revelar paths internos do servidor.

## Configuracao

Variaveis relevantes:

```env
LUME_CONNECT_ENABLED=True
LUME_CONNECT_MAX_IMAGE_MB=8
LUME_CONNECT_MAX_VIDEO_MB=80
LUME_CONNECT_MAX_SHORT_VIDEO_SECONDS=60
```

## Deploy

Atualizacao incremental recomendada:

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose restart web
```

Nao recrie banco, nao apague volumes Docker e nao remova migrations antigas.

Em VPS com Nginx/Cloudflare, confira tambem:

- limite de upload do Nginx (`client_max_body_size`) maior que `LUME_CONNECT_MAX_VIDEO_MB`;
- limite de upload/proxy do Cloudflare para o plano usado;
- persistencia do volume de media;
- backup do banco e da pasta de media antes de atualizacoes de producao.

## Evolucao futura

Pontos planejados para outra versao:

- Suporte WEBM validado com ferramenta externa.
- Geracao automatica de thumbnail.
- Transcodificacao e otimizacao por FFmpeg/ffprobe.
- HLS/adaptative streaming para videos maiores.
- Integracao oficial Meta/Instagram para contas profissionais, com OAuth e permissoes oficiais.
