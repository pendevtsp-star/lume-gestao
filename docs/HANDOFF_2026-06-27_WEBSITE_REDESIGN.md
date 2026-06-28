# Handoff Website Lume - 2026-06-27

## Objetivo desta rodada
- Refinar o visual do site publico da Lume antes de seguir para ajustes tecnicos finais e deploy em VPS.
- Prioridade do usuario: site mais limpo, slim, funcional e com melhor fluidez entre as secoes.

## Direcao aprovada para continuar
- Site publico segue no mesmo repositorio e no mesmo backend Django, no app `website`.
- `clinicafisiolume.com.br` fica para o site publico.
- `sistema.clinicafisiolume.com.br` continua como area operacional do sistema.
- CTA principal do site: WhatsApp `https://wa.me/message/GTYUJB6MIJJUJ1`
- CTA secundario: acesso ao sistema.
- Cidade correta: `Penedo/AL`

## O que foi ajustado nesta rodada
- Hero redesenhado com linguagem mais leve e comercial.
- Cabecalho refinado para integrar melhor a marca e evitar o efeito de logo solta no canto.
- Textos internos sobre "o layout do site" removidos e substituidos por copy voltada ao paciente.
- Secoes reorganizadas para reduzir redundancia e melhorar a leitura:
  - hero
  - atendimentos
  - experiencia Lume
  - reels/instagram
  - planos
  - CTA final
  - FAQ rapido
- Reels do Instagram mantidos como cards curados, sem embed pesado de feed.
- Responsividade revisada em viewport mobile real.

## Arquivos principais desta rodada
- `website/templates/website/home.html`
- `static/css/website.css`
- `website/views.py`

## Conteudo de preview local atualizado
- `hero_title`: `Movimento consciente para aliviar dores, ganhar forca e viver melhor.`
- `hero_subtitle`: copy mais humana e direta
- `institutional_title`: `Cuidado que acompanha cada fase do seu corpo.`
- `institutional_text`: copy institucional sem falar do proprio site

## Validacao feita
- `manage.py check` com SQLite local: OK
- `manage.py test website.tests`: OK
- Preview visual validada em desktop e mobile

## Preview local atual
- Site publico: `http://localhost:8010/`
- O servidor foi iniciado em background para revisao visual local

## Proximos passos sugeridos
1. Receber aprovacao visual do usuario.
2. Fazer ajustes finais de copy, imagens ou espacamento se necessario.
3. Revisar configuracoes de producao:
   - `ALLOWED_HOSTS`
   - `WEBSITE_HOSTS`
   - `SYSTEM_HOSTS`
   - `WEBSITE_BASE_URL`
   - `SYSTEM_BASE_URL`
   - Nginx
4. Publicar na VPS e validar dominio principal + subdominio do sistema.

## Observacoes
- Existem outras alteracoes no worktree que nao pertencem a esta rodada e nao devem ser revertidas sem alinhamento.
- Nao usar RJ em endereco/cidade; manter `Penedo/AL`.
