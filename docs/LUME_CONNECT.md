# Lume Connect

O Lume Connect e a rede social interna do sistema. Usuarios autenticados e ativos podem publicar posts, curtir e comentar conforme as permissoes ja existentes do modulo.

## Publicacao de video curto

Na tela do feed, use o formulario de publicacao e selecione o campo **Video curto**.

Limites atuais:

- Formatos aceitos: MP4, MOV e WEBM.
- Duracao maxima: 60 segundos por padrao (`LUME_CONNECT_MAX_SHORT_VIDEO_SECONDS`).
- Tamanho maximo: 80 MB por padrao (`LUME_CONNECT_MAX_VIDEO_MB`).
- Capa/thumbnail opcional: JPG, JPEG, PNG ou WEBP. Se nenhuma capa for enviada, o sistema gera uma automaticamente.

A validacao de duracao usa `ffprobe`. Apos validar, o backend usa `ffmpeg` para otimizar o arquivo e salvar o resultado em MP4 com `faststart`, codec H.264 e audio AAC. Se a duracao nao puder ser confirmada ou o processamento falhar, o upload e bloqueado com mensagem amigavel.

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
LUME_CONNECT_FFMPEG_PATH=ffmpeg
LUME_CONNECT_FFPROBE_PATH=ffprobe
LUME_CONNECT_FFMPEG_TIMEOUT_SECONDS=120
LUME_CONNECT_TRANSCODE_MAX_WIDTH=720
LUME_CONNECT_TRANSCODE_CRF=28
LUME_CONNECT_TRANSCODE_PRESET=veryfast
LUME_CONNECT_TRANSCODE_AUDIO_BITRATE=96k
```

O Dockerfile de producao instala `ffmpeg`. Em instalacoes sem Docker, instale `ffmpeg` e `ffprobe` no sistema operacional e confirme que ambos estao no `PATH`, ou ajuste `LUME_CONNECT_FFMPEG_PATH` e `LUME_CONNECT_FFPROBE_PATH`.

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
- CPU e memoria disponiveis para processar videos curtos durante o upload;
- persistencia do volume de media;
- backup do banco e da pasta de media antes de atualizacoes de producao.

## Evolucao futura

Pontos planejados para outra versao:

- HLS/adaptative streaming para videos maiores.
- Integracao oficial Meta/Instagram para contas profissionais, com OAuth e permissoes oficiais.
